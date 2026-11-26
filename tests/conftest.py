"""Ambiente comum dos testes: sem rede, sem Docker, sem chave e sem exportar traces."""
import os

import pytest

# varios modulos leem o ambiente no import: por isso isto vem antes de qualquer teste
os.environ.update({
    "LLM_API_KEY": "",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "",
    "OTEL_EXPORTER_OTLP_HEADERS": "",
    "TOKEN_INTERNO": "token-interno-de-teste",
    "JWT_SEGREDO": "segredo-de-teste-com-mais-de-32-bytes!!",
    "USUARIO_DEMO": "usuario-teste",
    "SENHA_DEMO": "senha-de-teste",
    "DESPERTAR_SERVICOS": "0",
    # retentativas sem espera real
    "BACKOFF_BASE": "0",
    # enderecos que nao existem: um teste que esqueca de substituir a rede falha na hora
    "REDIS_URL": "redis://127.0.0.1:1/0",
    "DATABASE_URL": "postgresql://teste:teste@127.0.0.1:1/teste",
    "URL_INFERENCIA": "http://inferencia.invalid",
    "URL_WORKER": "http://worker.invalid",
})


def _traces_em_memoria():
    """Instala o provedor antes de os apps serem importados, com a mesma limpeza de dados."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from comum.observabilidade import ExportadorSemDadosPessoais

    memoria = InMemorySpanExporter()
    provedor = TracerProvider()
    provedor.add_span_processor(SimpleSpanProcessor(ExportadorSemDadosPessoais(memoria)))
    trace.set_tracer_provider(provedor)
    return memoria


_SPANS = _traces_em_memoria()


@pytest.fixture
def spans():
    _SPANS.clear()
    return _SPANS


@pytest.fixture(autouse=True)
def disjuntores_novos(request, monkeypatch):
    """Os disjuntores sao do processo: cada teste comeca com os seus."""
    if request.node.get_closest_marker("e2e"):
        return  # fala com o sistema no ar: nao importa (nem instrumenta) os servicos
    from comum.circuit_breaker import CircuitBreaker
    from gateway import inferencia as do_gateway
    from inferencia import app as da_inferencia
    from worker import inferencia as do_worker

    for modulo, nome in ((do_gateway, "disjuntor"), (do_worker, "disjuntor"),
                         (da_inferencia, "disjuntor_llm")):
        monkeypatch.setattr(modulo, nome, CircuitBreaker(3, 20))
