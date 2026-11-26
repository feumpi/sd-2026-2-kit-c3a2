"""
Rastreamento distribuido (Aula 15): identificador do trace e propagacao pela fila.

A fila nao propaga contexto sozinha: o produtor grava o `traceparent` dentro da mensagem
e o consumidor o extrai antes de abrir o proprio span.
"""
from opentelemetry import propagate, trace


def id_do_trace() -> str:
    """Identificador do trace atual, para correlacionar logs; "-" se nao houver."""
    contexto = trace.get_current_span().get_span_context()
    return format(contexto.trace_id, "032x") if contexto.is_valid else "-"


def injetar_contexto() -> dict:
    """Contexto do span atual em formato serializavel, para viajar na mensagem."""
    portador: dict = {}
    propagate.inject(portador)
    return portador


def extrair_contexto(portador: dict | None):
    return propagate.extract(portador or {})
