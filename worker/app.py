"""
Worker de fila exposto como web service: o Render gratuito nao tem background worker.

O processo serve GET /saude (porta $PORT) e consome a fila numa thread, local e na nuvem.
"""
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from comum import contrato, web
from vetorial.repositorio import Repositorio
from worker.worker import consumir

web.configurar_logs()

redis_cliente = contrato.conectar()
repositorio = Repositorio()


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    parar = threading.Event()
    consumidor = threading.Thread(target=consumir, name="consumidor",
                                  args=(redis_cliente, repositorio, parar), daemon=True)
    consumidor.start()
    app.state.consumidor = consumidor
    yield
    # SIGTERM encerra o lifespan: a thread termina a tarefa atual e sai
    parar.set()
    consumidor.join(timeout=8)
    repositorio.fechar()


app = FastAPI(title="Worker - C3.A2", lifespan=ciclo_de_vida,
              docs_url=None, redoc_url=None, openapi_url=None)
web.exigir_token_interno(app)
web.registrar_requisicoes(app)


@app.get("/saude")
def saude():
    """Nao consulta dependencias: so informa se a thread consumidora esta viva."""
    thread = getattr(app.state, "consumidor", None)
    vivo = thread is not None and thread.is_alive()
    return JSONResponse(status_code=200 if vivo else 503,
                        content={"status": "ok" if vivo else "consumidor parado",
                                 "consumidor_vivo": vivo})
