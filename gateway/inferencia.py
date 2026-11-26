"""Encaminhamento das chamadas sincronas ao servico de inferencia (roteamento, Aula 8)."""
import logging
import os

import requests
from fastapi.responses import JSONResponse

from comum import web

log = logging.getLogger("gateway")

URL_INFERENCIA = os.getenv("URL_INFERENCIA", "http://inferencia:8001")
TIMEOUT = float(os.getenv("TIMEOUT_INFERENCIA", "10"))
TIMEOUT_CONEXAO = float(os.getenv("TIMEOUT_CONEXAO", "5"))

INDISPONIVEL = "servico de inferencia indisponivel; tente novamente em instantes"


def encaminhar(rota: str, corpo: dict) -> JSONResponse:
    """Repassa a requisicao. Falhas viram 503 generico, sem detalhes internos."""
    try:
        resposta = requests.post(f"{URL_INFERENCIA}{rota}", json=corpo,
                                 headers=web.cabecalhos_internos(),
                                 timeout=(TIMEOUT_CONEXAO, TIMEOUT))
    except requests.RequestException as erro:
        log.warning("falha ao chamar a inferencia: %s", type(erro).__name__)
        return web.indisponivel(INDISPONIVEL)
    return responder(resposta)


def corpo_json(resposta) -> dict | None:
    try:
        corpo = resposta.json()
    except ValueError:
        return None
    return corpo if isinstance(corpo, dict) else None


def responder(resposta) -> JSONResponse:
    corpo = corpo_json(resposta)
    if corpo is not None:
        if resposta.status_code in (200, 422):
            return JSONResponse(corpo, status_code=resposta.status_code)
        # degradacao elegante: a inferencia ja montou o que dava para responder
        if resposta.status_code == 503 and corpo.get("degradado"):
            return JSONResponse(corpo, status_code=503, headers={
                "Retry-After": resposta.headers.get("Retry-After", "5")})
    log.warning("resposta inesperada da inferencia: status=%d", resposta.status_code)
    return web.indisponivel(INDISPONIVEL)
