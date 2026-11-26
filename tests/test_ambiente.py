"""Sanidade do ambiente: dependencias instaladas e modulos reaproveitados importaveis."""
import importlib

import pytest

DEPENDENCIAS = [
    "fastapi", "uvicorn", "pydantic", "requests", "redis", "jwt", "sklearn", "joblib",
    "psycopg", "psycopg_pool", "fakeredis", "httpx",
    "opentelemetry.sdk.trace", "opentelemetry.exporter.otlp.proto.http.trace_exporter",
    "opentelemetry.instrumentation.fastapi", "opentelemetry.instrumentation.requests",
    "opentelemetry.instrumentation.psycopg",
]


@pytest.mark.parametrize("nome", DEPENDENCIAS)
def test_dependencia_importavel(nome):
    importlib.import_module(nome)


def test_modelo_do_kit_funciona_offline(monkeypatch, tmp_path):
    from inferencia import modelo

    monkeypatch.setattr(modelo, "CAMINHO", str(tmp_path / "modelo.joblib"))
    resultado = modelo.carregar_modelo().prever("o atendimento foi excelente")
    assert resultado["sentimento"] == "positivo"
