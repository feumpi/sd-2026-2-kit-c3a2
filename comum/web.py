"""
Pecas HTTP comuns aos servicos: log sem dado pessoal, erros genericos e token interno.

LGPD: o log leva so metodo, rota (o modelo, nao o caminho digitado), status, duracao e
trace_id. Nunca corpo, cabecalho, usuario ou IP. Rode o uvicorn com --no-access-log.
"""
import hmac
import logging
import os
import time
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from comum.observabilidade import id_do_trace

CABECALHO_INTERNO = "X-Token-Interno"
log = logging.getLogger("requisicoes")


def configurar_logs() -> None:
    logging.basicConfig(level=os.getenv("NIVEL_LOG", "INFO"),
                        format="%(asctime)s %(levelname)s [%(name)s] %(message)s")


def onde_falhou(erro: BaseException) -> str:
    """Tipo e linha do erro, sem a mensagem (que pode conter dados da requisicao)."""
    pilha = traceback.extract_tb(erro.__traceback__)
    if not pilha:
        return type(erro).__name__
    ultimo = pilha[-1]
    return f"{type(erro).__name__} em {os.path.basename(ultimo.filename)}:{ultimo.lineno}"


def cabecalhos_internos() -> dict:
    """Cabecalhos das chamadas entre servicos."""
    return {CABECALHO_INTERNO: os.getenv("TOKEN_INTERNO", "")}


def indisponivel(mensagem: str, espera: float = 5, **extras) -> JSONResponse:
    """Degradacao elegante: 503 com Retry-After e o que ja se sabe."""
    return JSONResponse(status_code=503,
                        headers={"Retry-After": str(max(1, round(espera)))},
                        content={"erro": mensagem, **extras})


def exigir_token_interno(app: FastAPI, livres: tuple = ("/saude",)) -> None:
    """Recusa com 401 qualquer chamada sem o token interno (Zero Trust, Aula 16)."""
    @app.middleware("http")
    async def conferir(request: Request, call_next):
        esperado = os.getenv("TOKEN_INTERNO", "")
        recebido = request.headers.get(CABECALHO_INTERNO, "")
        if request.url.path not in livres and not (
            esperado and hmac.compare_digest(recebido.encode(), esperado.encode())
        ):
            return JSONResponse(status_code=401, content={"erro": "token interno invalido"})
        return await call_next(request)


def registrar_requisicoes(app: FastAPI) -> None:
    """Log por requisicao e tratamento de erros. Chame por ultimo: fica por fora de tudo."""
    @app.exception_handler(RequestValidationError)
    async def entrada_invalida(request: Request, erro: RequestValidationError):
        # sem o campo "input": nao devolve nem propaga o que foi digitado
        detalhes = [{"campo": ".".join(str(p) for p in e["loc"]), "mensagem": e["msg"]}
                    for e in erro.errors()]
        return JSONResponse(status_code=422, content={"erro": "entrada invalida",
                                                      "detalhes": detalhes})

    @app.middleware("http")
    async def registrar(request: Request, call_next):
        inicio = time.perf_counter()
        try:
            resposta = await call_next(request)
        except Exception as erro:
            log.error("erro nao tratado: %s trace_id=%s", onde_falhou(erro), id_do_trace())
            resposta = JSONResponse(status_code=500, content={"erro": "erro interno"})
        rota = getattr(request.scope.get("route"), "path", "-")
        # as verificacoes de saude se repetem a cada poucos segundos: so em depuracao
        rotina = rota == "/saude" and resposta.status_code < 400
        log.log(logging.DEBUG if rotina else logging.INFO,
                "metodo=%s rota=%s status=%d duracao_ms=%.1f trace_id=%s",
                request.method, rota, resposta.status_code,
                (time.perf_counter() - inicio) * 1000, id_do_trace())
        return resposta
