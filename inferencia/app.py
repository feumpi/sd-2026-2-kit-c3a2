"""
Servico de inferencia: unico lugar com modelo, embeddings e LLM (Aula 6).

  POST /predict    sentimento de um texto
  POST /processar  sentimento + vetor de um documento (usado pelo worker)
  POST /buscar     documentos mais parecidos com a pergunta
  POST /perguntar  RAG: resposta fundamentada nos documentos, com as fontes
  GET  /saude      estado do servico (unica rota sem token interno)

Le o banco vetorial, nunca grava. A chamada ao LLM tem tempo-limite, retentativa e
disjuntor (Aula 11). Falha de dependencia vira 503 com `degradado: true`.
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

from comum import observabilidade, web
from comum.circuit_breaker import CircuitBreaker, CircuitoAberto
from comum.modelos import Consulta, EntradaTexto
from comum.resiliencia import com_retentativa
from inferencia import llm
from inferencia.embeddings import Vetorizador
from inferencia.modelo import ModeloSentimento, carregar_modelo
from vetorial.repositorio import BancoIndisponivel, EsquemaAusente, Repositorio

web.configurar_logs()
PsycopgInstrumentor().instrument()  # antes de o pool abrir a primeira conexao
log = logging.getLogger("inferencia")

SEM_BASE = "Nao encontrei nos documentos indexados nada sobre essa pergunta."

modelo: ModeloSentimento | None = None
vetorizador = Vetorizador()
repositorio = Repositorio()

# busca no banco (DB_TIMEOUT) + LLM precisam caber no tempo-limite do gateway, senao ele
# desiste antes
LLM_PRAZO_TOTAL = float(os.getenv("LLM_PRAZO_TOTAL", "4"))
RETENTATIVAS = int(os.getenv("RETENTATIVAS", "3"))
BACKOFF_BASE = float(os.getenv("BACKOFF_BASE", "0.5"))
disjuntor_llm = CircuitBreaker(limite_falhas=int(os.getenv("LIMITE_FALHAS", "3")),
                               espera_segundos=float(os.getenv("ESPERA_DISJUNTOR", "20")))


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    """Carrega o modelo UMA vez, na subida, e nao a cada requisicao."""
    global modelo
    modelo = carregar_modelo()
    log.info("modelo carregado")
    yield
    repositorio.fechar()
    observabilidade.encerrar()


app = FastAPI(title="Inferencia - C3.A2", lifespan=ciclo_de_vida,
              docs_url=None, redoc_url=None, openapi_url=None)
web.exigir_token_interno(app)
web.registrar_requisicoes(app)
observabilidade.configurar(app, "inferencia")


def prever(texto: str) -> dict:
    assert modelo is not None, "o modelo e carregado na subida"
    return modelo.prever(texto)


@app.post("/predict")
def predict(entrada: EntradaTexto):
    return prever(entrada.texto)


@app.post("/processar")
def processar(entrada: EntradaTexto):
    vetor = vetorizador.vetorizar(entrada.texto)
    if not any(vetor):
        # vetor zerado daria NaN na distancia do cosseno
        raise HTTPException(422, "texto sem palavras que possam ser indexadas")
    resultado = prever(entrada.texto)
    return {"sentimento": resultado["sentimento"], "confianca": resultado["confianca"],
            "vetor": vetor}


def recuperar(consulta: Consulta) -> list[dict]:
    """Documentos relevantes; lista vazia se nao ha base. Levanta BancoIndisponivel."""
    vetor = vetorizador.vetorizar(consulta.pergunta)
    if not any(vetor):
        return []
    try:
        linhas = repositorio.buscar(vetor, consulta.top_k)
    except EsquemaAusente:
        return []
    # sem nada em comum com a pergunta, o trecho nao fundamenta resposta
    return [{**linha, "score": round(float(linha["score"]), 4)}
            for linha in linhas if linha["score"] > 0]


def banco_fora(erro: BancoIndisponivel):
    log.warning("banco vetorial indisponivel: %s", erro)
    return web.indisponivel("armazenamento vetorial indisponivel", degradado=True)


@app.post("/buscar")
def buscar(consulta: Consulta):
    try:
        return {"resultados": recuperar(consulta)}
    except BancoIndisponivel as erro:
        return banco_fora(erro)


def gerar_resposta(pergunta: str, contexto: list) -> str:
    """Gerar nao tem efeito colateral: pode ser repetido."""
    tentar = com_retentativa(llm.gerar, tentativas=RETENTATIVAS, base=BACKOFF_BASE,
                             prazo_total=LLM_PRAZO_TOTAL, tempo_limite=llm.TIMEOUT)
    return disjuntor_llm.chamar(tentar, pergunta, contexto)


@app.post("/perguntar")
def perguntar(consulta: Consulta):
    try:
        resultados = recuperar(consulta)
    except BancoIndisponivel as erro:
        return banco_fora(erro)
    contexto = [r["texto"] for r in resultados]
    fontes = list(dict.fromkeys(r["origem"] for r in resultados))
    if not contexto:
        return {"resposta": SEM_BASE, "contexto": [], "fontes": []}
    try:
        resposta = gerar_resposta(consulta.pergunta, contexto)
    except Exception as erro:
        if not isinstance(erro, CircuitoAberto):
            log.warning("falha ao chamar o LLM: %s", type(erro).__name__)
        return web.indisponivel("LLM indisponivel no momento; seguem os trechos recuperados",
                                espera=disjuntor_llm.segundos_para_tentar() or 5,
                                degradado=True, contexto=contexto, fontes=fontes)
    return {"resposta": resposta, "contexto": contexto, "fontes": fontes}


@app.get("/saude")
def saude():
    return {"status": "ok", "modelo_carregado": modelo is not None,
            "llm": "api" if llm.API_KEY else "simulado",
            "disjuntores": {"llm": disjuntor_llm.estado}}
