"""
Consumidor da fila (Aula 8): pede o processamento a inferencia e grava no banco vetorial.

E o unico escritor do banco. Reprocessar e seguro porque a gravacao e idempotente.

Falhas:
  - transitoria (tempo-limite, conexao, 5xx, 429, circuito aberto, banco fora): espera e
    reenfileira SEM
    gastar tentativa; so vai a dead-letter ao passar de TAREFA_IDADE_MAXIMA. Assim o cold
    start da inferencia nao descarta tarefas boas;
  - permanente (4xx, erro nos dados): ate MAX_TENTATIVAS, depois dead-letter;
  - mensagem malformada: direto para a dead-letter.
"""
import json
import logging
import os
import random
import threading
import time

import redis
from opentelemetry.trace import StatusCode

from comum.circuit_breaker import CircuitoAberto
from comum.observabilidade import span_consumidor
from comum.resiliencia import eh_transitoria
from comum.web import onde_falhou
from vetorial.repositorio import BancoIndisponivel, EsquemaAusente
from worker import fila, inferencia

log = logging.getLogger("worker")

MAX_TENTATIVAS = int(os.getenv("MAX_TENTATIVAS", "3"))
IDADE_MAXIMA = float(os.getenv("TAREFA_IDADE_MAXIMA", "900"))
BACKOFF_BASE = float(os.getenv("BACKOFF_BASE", "0.5"))
ESPERA_MAXIMA = float(os.getenv("ESPERA_MAXIMA", "30"))
RETENCAO_DIAS = float(os.getenv("RETENCAO_DIAS", "30"))
INTERVALO_EXPURGO = float(os.getenv("INTERVALO_EXPURGO", "3600"))
ESPERA_FILA = 2  # menor que o tempo-limite do cliente Redis
PAUSA_FALHA = 2


def ler_mensagem(original: str) -> dict:
    """Valida o formato da mensagem; levanta ValueError se estiver malformada."""
    try:
        tarefa = json.loads(original)
        documento = tarefa["documento"]
        if not all(isinstance(v, str) and v
                   for v in (tarefa["id"], documento["texto"], documento["origem"])):
            raise ValueError("campo vazio ou de tipo errado")
        tarefa["tentativas"] = int(tarefa.get("tentativas", 0))
        tarefa["criada_em"] = float(tarefa["criada_em"])
    except (KeyError, TypeError, ValueError) as erro:
        raise ValueError("mensagem invalida") from erro
    return tarefa


def executar(tarefa: dict, repositorio) -> dict:
    documento = tarefa["documento"]
    analise = inferencia.processar(documento["texto"])
    documento_id, novo = repositorio.gravar(
        documento["texto"], documento["origem"], analise["sentimento"],
        analise["confianca"], analise["vetor"])
    return {"documento_id": documento_id, "novo": int(novo),
            "sentimento": analise["sentimento"], "confianca": analise["confianca"]}


def falha_transitoria(erro: Exception) -> bool:
    return isinstance(erro, (BancoIndisponivel, CircuitoAberto)) or eh_transitoria(erro)


def espera_do_adiamento(adiamentos: int, erro: Exception) -> float:
    """Backoff exponencial com teto e jitter; com circuito aberto, o tempo que ele pede."""
    if isinstance(erro, CircuitoAberto):
        return max(1.0, inferencia.disjuntor.segundos_para_tentar())
    espera = min(BACKOFF_BASE * 2 ** min(adiamentos - 1, 10), ESPERA_MAXIMA)
    return espera + random.uniform(0, BACKOFF_BASE)


def tratar_falha(r, original: str, tarefa: dict, erro: Exception,
                 parar: threading.Event) -> None:
    motivo = type(erro).__name__  # a mensagem do erro pode conter dados (LGPD)
    if falha_transitoria(erro):
        if time.time() - tarefa["criada_em"] > IDADE_MAXIMA:
            fila.descartar(r, original, tarefa["id"], f"prazo esgotado ({motivo})",
                           json.dumps(tarefa))
            return
        tarefa["adiamentos"] = tarefa.get("adiamentos", 0) + 1
        espera = espera_do_adiamento(tarefa["adiamentos"], erro)
        log.warning("tarefa %s adiada por falha transitoria (%s); espera de %.1fs",
                    tarefa["id"], motivo, espera)
        parar.wait(espera)
        fila.reenfileirar(r, original, tarefa, motivo)
        return
    tarefa["tentativas"] += 1
    if tarefa["tentativas"] >= MAX_TENTATIVAS:
        fila.descartar(r, original, tarefa["id"], motivo, json.dumps(tarefa))
        return
    log.warning("tarefa %s falhou (%s), tentativa %d/%d", tarefa["id"], motivo,
                tarefa["tentativas"], MAX_TENTATIVAS)
    fila.reenfileirar(r, original, tarefa, motivo)


def processar_uma(r, repositorio, parar: threading.Event, espera: int = ESPERA_FILA) -> bool:
    """Processa uma mensagem. Devolve False se a fila ficou vazia."""
    original = fila.retirar(r, espera)
    if original is None:
        return False
    try:
        tarefa = ler_mensagem(original)
    except ValueError:
        fila.descartar(r, original, None, "mensagem invalida")
        return True
    # continua o trace de quem publicou; o laco ocioso nao gera spans
    with span_consumidor(tarefa.get("contexto_trace")) as span:
        span.set_attribute("tarefa.id", tarefa["id"])
        try:
            resultado = executar(tarefa, repositorio)
        except Exception as erro:
            span.set_status(StatusCode.ERROR)
            span.set_attribute("tarefa.falha", type(erro).__name__)
            if isinstance(erro, EsquemaAusente):
                repositorio.aplicar_esquema()
            tratar_falha(r, original, tarefa, erro, parar)
            return True
        fila.concluir(r, original, tarefa["id"], **resultado)
        log.info("tarefa %s concluida", tarefa["id"])
        return True


def expurgar(r, repositorio) -> None:
    """Retencao (LGPD): documentos antigos no banco e entradas antigas da dead-letter."""
    documentos = repositorio.expurgar(RETENCAO_DIAS)
    descartes = fila.expurgar_dlq(r)
    log.info("expurgo: %d documento(s) e %d entrada(s) da dead-letter", documentos, descartes)


def consumir(r, repositorio, parar: threading.Event) -> None:
    """Laco principal: prepara o banco, expurga periodicamente e consome a fila."""
    esquema_pronto = recuperado = False
    proximo_expurgo = 0.0
    log.info("consumidor aguardando tarefas")
    while not parar.is_set():
        try:
            if not esquema_pronto:
                repositorio.aplicar_esquema()
                esquema_pronto = True
            if time.monotonic() >= proximo_expurgo:
                expurgar(r, repositorio)
                proximo_expurgo = time.monotonic() + INTERVALO_EXPURGO
            if not recuperado:
                fila.recuperar_pendentes(r)
                recuperado = True
            processar_uma(r, repositorio, parar)
        except (redis.RedisError, BancoIndisponivel) as erro:
            # a mensagem em andamento fica em "processando": recupere na proxima volta
            recuperado = False
            log.warning("dependencia indisponivel (%s); nova tentativa em %ds",
                        type(erro).__name__, PAUSA_FALHA)
            parar.wait(PAUSA_FALHA)
        except Exception as erro:
            recuperado = False
            log.error("falha inesperada no consumidor: %s", onde_falhou(erro))
            parar.wait(PAUSA_FALHA)
