"""
API Gateway - porta de entrada unica da plataforma (Aula 8).

  POST /login          emite o token JWT (as rotas abaixo, menos /saude, o exigem)
                       (login limitado por IP; rotas protegidas, por usuario: 429)
  POST /predict        sentimento (sincrono, via inferencia)
  POST /documentos     indexacao assincrona: devolve 202 e o id da tarefa (via fila)
  GET  /tarefas/{id}   estado da tarefa
  POST /buscar         documentos mais parecidos com a pergunta
  POST /perguntar      resposta fundamentada nos documentos (RAG)
  GET  /saude          estado do gateway, sem depender de outros servicos

Rodar: uvicorn gateway.app:app --port 8000 --no-access-log
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated

import redis
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path
from fastapi.responses import HTMLResponse, RedirectResponse

from comum import contrato, observabilidade, web
from comum.modelos import Consulta, Documento, EntradaTexto
from gateway import autenticacao, inferencia, limite, pagina
from gateway.despertar import despertar

web.configurar_logs()
log = logging.getLogger("gateway")

URL_WORKER = os.getenv("URL_WORKER", "http://worker:8002")
FILA_FORA = "fila de tarefas indisponivel; tente novamente em instantes"

redis_cliente = contrato.conectar()


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    autenticacao.segredo()  # sem segredo forte o gateway nem sobe
    despertar(inferencia.URL_INFERENCIA, URL_WORKER)
    yield
    observabilidade.encerrar()


app = FastAPI(title="Plataforma de IA - Gateway C3.A2", lifespan=ciclo_de_vida)
app.state.redis = lambda: redis_cliente  # lido a cada uso: os testes trocam o cliente
# toda rota de negocio entra neste roteador: exige token e conta no limite do usuario
protegidas = APIRouter(dependencies=[Depends(limite.limitar_usuario)])


@app.get("/", include_in_schema=False)
def inicio():
    """Documentacao; na nuvem, antes passa pela pagina que acorda os outros servicos."""
    html = pagina.montar((inferencia.URL_INFERENCIA, URL_WORKER))
    return HTMLResponse(html) if html else RedirectResponse("/docs")


@app.get("/saude")
def saude():
    """Rapido e sem chamar ninguem: so mostra o estado dos disjuntores."""
    return {"status": "ok", "disjuntores": {"inferencia": inferencia.disjuntor.estado}}


@protegidas.post("/predict")
def predict(entrada: EntradaTexto):
    return inferencia.encaminhar("/predict", entrada.model_dump())


@protegidas.post("/documentos", status_code=202)
def enviar_documento(documento: Documento):
    """Enfileira o documento; acompanhe em GET /tarefas/{id}."""
    try:
        with observabilidade.span_produtor() as (span, contexto):
            tarefa_id = contrato.enfileirar(redis_cliente, documento.model_dump(), contexto)
            span.set_attribute("tarefa.id", tarefa_id)
    except redis.RedisError as erro:
        log.warning("fila indisponivel: %s", type(erro).__name__)
        return web.indisponivel(FILA_FORA)
    despertar(URL_WORKER)
    return {"id": tarefa_id, "estado": contrato.PENDENTE,
            "acompanhar": f"/tarefas/{tarefa_id}"}


@protegidas.get("/tarefas/{tarefa_id}")
def consultar_tarefa(tarefa_id: Annotated[str, Path(max_length=64)]):
    try:
        dados = contrato.consultar_tarefa(redis_cliente, tarefa_id)
    except redis.RedisError as erro:
        log.warning("fila indisponivel: %s", type(erro).__name__)
        return web.indisponivel(FILA_FORA)
    if dados is None:
        raise HTTPException(404, "tarefa inexistente ou expirada")
    if dados.get("estado") == contrato.PENDENTE:
        despertar(URL_WORKER)  # sem trafego o worker dorme e a fila acumula
    return {"id": tarefa_id, **dados}


@protegidas.post("/buscar")
def buscar(consulta: Consulta):
    return inferencia.encaminhar("/buscar", consulta.model_dump())


@protegidas.post("/perguntar")
def perguntar(consulta: Consulta):
    return inferencia.encaminhar("/perguntar", consulta.model_dump())


app.include_router(autenticacao.roteador, dependencies=[Depends(limite.limitar_endereco)])
app.include_router(protegidas)
web.registrar_requisicoes(app)
observabilidade.configurar(app, "gateway")
