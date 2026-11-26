"""Ambiente comum dos testes: sem rede, sem Docker, sem chave e sem exportar traces."""
import os

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
    # enderecos que nao existem: um teste que esqueca de substituir a rede falha na hora
    "REDIS_URL": "redis://127.0.0.1:1/0",
    "DATABASE_URL": "postgresql://teste:teste@127.0.0.1:1/teste",
    "URL_INFERENCIA": "http://inferencia.invalid",
    "URL_WORKER": "http://worker.invalid",
})
