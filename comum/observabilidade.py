"""
Rastreamento distribuido com OpenTelemetry (Aula 15), igual nos tres servicos.

  - configurar(app, servico): provedor, exportador OTLP e instrumentacao HTTP;
  - a fila nao propaga contexto sozinha: o produtor grava o `traceparent` dentro da
    mensagem (span_produtor) e o consumidor o extrai (span_consumidor);
  - todo registro de log leva o trace_id;
  - LGPD: IP, agente do usuario, URL recebida e mensagens de erro saem dos spans antes da
    exportacao.

Configurado so por ambiente: OTEL_SERVICE_NAME, OTEL_EXPORTER_OTLP_ENDPOINT e
OTEL_EXPORTER_OTLP_HEADERS. Sem endpoint nada e exportado.
"""
import logging
import os
from contextlib import contextmanager

from fastapi import FastAPI
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import SpanKind, Status

from comum.contrato import FILA

ATRIBUTOS_PESSOAIS = frozenset({
    "net.peer.ip", "net.peer.port", "net.sock.peer.addr", "net.sock.peer.port",
    "client.address", "client.port", "http.client_ip", "network.peer.address",
    "network.peer.port", "http.user_agent", "user_agent.original",
})
# no span de entrada, o caminho e a consulta sao escritos pelo cliente: fica so http.route
ENDERECO_RECEBIDO = frozenset({"http.url", "http.target", "url.full", "url.path", "url.query"})

rastreador = trace.get_tracer("plataforma-ia")


def _limpar_atributos(span: ReadableSpan) -> dict:
    limpos = {}
    for chave, valor in (span.attributes or {}).items():
        if chave in ATRIBUTOS_PESSOAIS:
            continue
        if chave in ENDERECO_RECEBIDO:
            if span.kind == SpanKind.SERVER or chave == "url.query":
                continue
            valor = str(valor).split("?", 1)[0]
        limpos[chave] = valor
    return limpos


def sem_dados_pessoais(span: ReadableSpan) -> ReadableSpan:
    """Copia do span sem dados pessoais (o original e somente leitura depois de encerrado)."""
    eventos = [
        Event(e.name, {k: v for k, v in (e.attributes or {}).items() if k == "exception.type"},
              e.timestamp)
        for e in span.events
    ]
    return ReadableSpan(
        name=span.name, context=span.context, parent=span.parent, resource=span.resource,
        attributes=_limpar_atributos(span), events=eventos, links=span.links, kind=span.kind,
        status=Status(span.status.status_code),  # sem a descricao: pode repetir dados
        start_time=span.start_time, end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


def _ruido(span: ReadableSpan) -> bool:
    """A checagem de conexao do pool e uma consulta vazia: nao diz nada no trace."""
    atributos = span.attributes or {}
    return "db.system" in atributos and not atributos.get("db.statement")


class ExportadorSemDadosPessoais(SpanExporter):
    """Envolve outro exportador e limpa cada span antes de entregar."""

    def __init__(self, destino: SpanExporter):
        self.destino = destino

    def export(self, spans):
        return self.destino.export([sem_dados_pessoais(s) for s in spans if not _ruido(s)])

    def shutdown(self):
        self.destino.shutdown()

    def force_flush(self, timeout_millis: int = 30000):
        return self.destino.force_flush(timeout_millis)


def iniciar_rastreamento(servico: str) -> None:
    """Instala o provedor de traces uma unica vez por processo."""
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return
    atributos = {} if os.getenv("OTEL_SERVICE_NAME") else {"service.name": servico}
    provedor = TracerProvider(resource=Resource.create(atributos))
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        provedor.add_span_processor(
            BatchSpanProcessor(ExportadorSemDadosPessoais(OTLPSpanExporter())))
    trace.set_tracer_provider(provedor)


def configurar(app: FastAPI, servico: str) -> None:
    """Rastreia as requisicoes recebidas (menos /saude) e as feitas com `requests`."""
    iniciar_rastreamento(servico)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="saude",
                                       exclude_spans=["receive", "send"])
    instrumentador = RequestsInstrumentor()
    if not instrumentador.is_instrumented_by_opentelemetry:
        instrumentador.instrument()


def encerrar() -> None:
    """Envia o que ainda esta no lote antes de o processo parar."""
    provedor = trace.get_tracer_provider()
    if isinstance(provedor, TracerProvider):
        provedor.force_flush(5000)


def id_do_trace() -> str:
    """Identificador do trace atual, para correlacionar logs; "-" se nao houver."""
    contexto = trace.get_current_span().get_span_context()
    return format(contexto.trace_id, "032x") if contexto.is_valid else "-"


def correlacionar_logs() -> None:
    """Acrescenta o atributo `trace_id` a todo registro de log do processo."""
    anterior = logging.getLogRecordFactory()
    if getattr(anterior, "com_trace_id", False):
        return

    def fabrica(*args, **kwargs):
        registro = anterior(*args, **kwargs)
        registro.trace_id = id_do_trace()
        return registro

    fabrica.com_trace_id = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(fabrica)


def injetar_contexto() -> dict:
    """Contexto do span atual em formato serializavel, para viajar na mensagem."""
    portador: dict = {}
    propagate.inject(portador)
    return portador


def extrair_contexto(portador: dict | None):
    return propagate.extract(portador or {})


def _atributos_da_fila() -> dict:
    return {"messaging.system": "redis", "messaging.destination.name": FILA}


@contextmanager
def span_produtor():
    """Span da publicacao: devolve (span, contexto a gravar na mensagem)."""
    with rastreador.start_as_current_span(
        f"publicar {FILA}", kind=SpanKind.PRODUCER, attributes=_atributos_da_fila()
    ) as span:
        yield span, injetar_contexto()


@contextmanager
def span_consumidor(portador: dict | None):
    """Span do processamento, filho do span que publicou a mensagem."""
    with rastreador.start_as_current_span(
        f"processar {FILA}", context=extrair_contexto(portador), kind=SpanKind.CONSUMER,
        attributes=_atributos_da_fila(),
    ) as span:
        yield span
