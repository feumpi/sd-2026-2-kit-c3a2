"""
Encaminhamento das chamadas sincronas a inferencia (Aula 8), com resiliencia (Aula 11).

disjuntor -> retentativa -> chamada com tempo-limite. As rotas repassadas so leem, entao
repetir e seguro. Contam como falha o erro de transporte e o 5xx nao tratado; um 4xx ou a
resposta degradada (a inferencia esta de pe, outra dependencia nao) nao abrem o circuito.
"""
import logging
import os

import requests
from fastapi.responses import JSONResponse

from comum import web
from comum.circuit_breaker import CircuitBreaker, CircuitoAberto
from comum.resiliencia import com_retentativa

log = logging.getLogger("gateway")

URL_INFERENCIA = os.getenv("URL_INFERENCIA", "http://inferencia:8001")
TIMEOUT = float(os.getenv("TIMEOUT_INFERENCIA", "10"))
TIMEOUT_CONEXAO = float(os.getenv("TIMEOUT_CONEXAO", "5"))
# teto da sequencia inteira: tempo-limite longo nao se multiplica pelas tentativas
PRAZO_TOTAL = float(os.getenv("PRAZO_INFERENCIA") or TIMEOUT * 1.5)
RETENTATIVAS = int(os.getenv("RETENTATIVAS", "3"))
BACKOFF_BASE = float(os.getenv("BACKOFF_BASE", "0.5"))

disjuntor = CircuitBreaker(limite_falhas=int(os.getenv("LIMITE_FALHAS", "3")),
                           espera_segundos=float(os.getenv("ESPERA_DISJUNTOR", "20")))

INDISPONIVEL = "servico de inferencia indisponivel; tente novamente em instantes"


def chamar(rota: str, corpo: dict, tempo_limite: float) -> requests.Response:
    """Uma tentativa. Levanta requests.RequestException no que conta como falha."""
    resposta = requests.post(f"{URL_INFERENCIA}{rota}", json=corpo,
                             headers=web.cabecalhos_internos(),
                             timeout=(min(TIMEOUT_CONEXAO, tempo_limite), tempo_limite))
    codigo = resposta.status_code
    if codigo == 429 or (codigo >= 500 and not degradada(resposta)):
        raise requests.HTTPError(f"HTTP {codigo}", response=resposta)
    return resposta


def encaminhar(rota: str, corpo: dict) -> JSONResponse:
    """Repassa a requisicao. Falhas viram 503 generico, sem detalhes internos."""
    tentar = com_retentativa(chamar, tentativas=RETENTATIVAS, base=BACKOFF_BASE,
                             prazo_total=PRAZO_TOTAL, tempo_limite=TIMEOUT)
    try:
        resposta = disjuntor.chamar(tentar, rota, corpo)
    except CircuitoAberto:
        return web.indisponivel(INDISPONIVEL, espera=disjuntor.segundos_para_tentar() or 5)
    except requests.RequestException as erro:
        log.warning("falha ao chamar a inferencia: %s", type(erro).__name__)
        return web.indisponivel(INDISPONIVEL, espera=disjuntor.segundos_para_tentar() or 5)
    return responder(resposta)


def corpo_json(resposta) -> dict | None:
    try:
        corpo = resposta.json()
    except ValueError:
        return None
    return corpo if isinstance(corpo, dict) else None


def degradada(resposta) -> bool:
    """503 montado pela propria inferencia, com o que ela conseguiu responder."""
    corpo = corpo_json(resposta)
    return resposta.status_code == 503 and bool(corpo and corpo.get("degradado"))


def responder(resposta) -> JSONResponse:
    corpo = corpo_json(resposta)
    if corpo is not None:
        if resposta.status_code in (200, 422):
            return JSONResponse(corpo, status_code=resposta.status_code)
        # degradacao elegante: a inferencia ja montou o que dava para responder
        if degradada(resposta):
            return JSONResponse(corpo, status_code=503, headers={
                "Retry-After": resposta.headers.get("Retry-After", "5")})
    log.warning("resposta inesperada da inferencia: status=%d", resposta.status_code)
    return web.indisponivel(INDISPONIVEL)
