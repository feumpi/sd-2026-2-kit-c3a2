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


@pytest.fixture(autouse=True)
def disjuntores_novos(monkeypatch):
    """Os disjuntores sao do processo: cada teste comeca com os seus."""
    from comum.circuit_breaker import CircuitBreaker
    from gateway import inferencia as do_gateway
    from inferencia import app as da_inferencia
    from worker import inferencia as do_worker

    for modulo, nome in ((do_gateway, "disjuntor"), (do_worker, "disjuntor"),
                         (da_inferencia, "disjuntor_llm")):
        monkeypatch.setattr(modulo, nome, CircuitBreaker(3, 20))
