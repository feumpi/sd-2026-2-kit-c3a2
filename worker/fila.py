"""
Lado consumidor da fila (Aula 8). O contrato (chaves e mensagem) esta em comum/contrato.py.

Fila confiavel: a mensagem e movida atomicamente (BLMOVE) para a lista "processando" e so
sai de la, na mesma transacao que grava o resultado, o reenfileiramento ou o descarte.
Se o worker cair no meio, ela volta para a fila quando ele subir de novo.
`recuperar_pendentes` pressupoe um unico worker.
"""
import json
import logging
import os
import time
from typing import cast

from comum import contrato

log = logging.getLogger("worker")

# a dead-letter guarda o texto: o prazo dela tambem e limitado (LGPD)
DLQ_RETENCAO = float(os.getenv("DLQ_RETENCAO_DIAS", "7")) * 24 * 60 * 60


def retirar(r, espera: int) -> str | None:
    """Proxima mensagem, ja registrada como em processamento; None se a fila ficou vazia."""
    mensagem = r.blmove(contrato.FILA, contrato.PROCESSANDO, espera, "RIGHT", "LEFT")
    if mensagem is not None:
        r.expire(contrato.PROCESSANDO, contrato.VALIDADE_TAREFA)
    return cast("str | None", mensagem)


def recuperar_pendentes(r) -> int:
    """Devolve para a fila o que ficou em 'processando' de uma execucao anterior."""
    recuperadas = 0
    while r.lmove(contrato.PROCESSANDO, contrato.FILA, "RIGHT", "RIGHT") is not None:
        recuperadas += 1
    if recuperadas:
        log.warning("%d tarefa(s) interrompida(s) devolvida(s) a fila", recuperadas)
    return recuperadas


def concluir(r, original: str, tarefa_id: str, **resultado) -> None:
    with r.pipeline(transaction=True) as lote:
        contrato.atualizar_tarefa(lote, tarefa_id, estado=contrato.CONCLUIDA,
                                  concluida_em=time.time(), erro="", **resultado)
        lote.lrem(contrato.PROCESSANDO, 1, original)
        lote.execute()


def reenfileirar(r, original: str, tarefa: dict, motivo: str) -> None:
    with r.pipeline(transaction=True) as lote:
        contrato.atualizar_tarefa(lote, tarefa["id"], estado=contrato.PENDENTE,
                                  tentativas=tarefa["tentativas"], erro=motivo)
        lote.lpush(contrato.FILA, json.dumps(tarefa))
        lote.expire(contrato.FILA, contrato.VALIDADE_TAREFA)
        lote.lrem(contrato.PROCESSANDO, 1, original)
        lote.execute()


def descartar(r, original: str, tarefa_id: str | None, motivo: str,
              mensagem: str | None = None) -> None:
    """Manda para a dead-letter. `motivo` e uma categoria, nunca o conteudo do erro."""
    entrada = {"mensagem": mensagem or original, "motivo": motivo, "em": time.time()}
    with r.pipeline(transaction=True) as lote:
        lote.lpush(contrato.DLQ, json.dumps(entrada))
        lote.expire(contrato.DLQ, int(DLQ_RETENCAO))
        if tarefa_id:
            contrato.atualizar_tarefa(lote, tarefa_id, estado=contrato.FALHOU, erro=motivo)
        lote.lrem(contrato.PROCESSANDO, 1, original)
        lote.execute()
    log.error("tarefa %s enviada para a dead-letter: %s", tarefa_id or "(ilegivel)", motivo)


def expurgar_dlq(r) -> int:
    """Remove da dead-letter o que passou do prazo (as mais antigas ficam no fim)."""
    limite = time.time() - DLQ_RETENCAO
    removidas = 0
    while (antiga := r.lindex(contrato.DLQ, -1)) is not None:
        try:
            if json.loads(cast(str, antiga))["em"] > limite:
                break
        except (ValueError, KeyError, TypeError):
            pass  # entrada ilegivel tambem sai
        r.rpop(contrato.DLQ)
        removidas += 1
    return removidas
