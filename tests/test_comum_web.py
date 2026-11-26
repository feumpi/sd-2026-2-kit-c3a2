"""Testes das pecas HTTP comuns: log sem dado pessoal, erros genericos e token interno."""
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from comum import web
from comum.modelos import TEXTO_MAXIMO, EntradaTexto

TOKEN = {"X-Token-Interno": "token-interno-de-teste"}


@pytest.fixture
def cliente():
    app = FastAPI()

    @app.get("/saude")
    def saude():
        return {"status": "ok"}

    @app.post("/eco/{nome}")
    def eco(nome: str, entrada: EntradaTexto):
        return {"texto": entrada.texto}

    @app.get("/quebra")
    def quebra():
        raise RuntimeError("detalhe sigiloso do erro")

    web.exigir_token_interno(app)
    web.registrar_requisicoes(app)
    return TestClient(app)


def test_saude_dispensa_token(cliente):
    assert cliente.get("/saude").status_code == 200


@pytest.mark.parametrize("cabecalho", [{}, {"X-Token-Interno": "errado"}])
def test_sem_token_valido_da_401(cliente, cabecalho):
    assert cliente.get("/quebra", headers=cabecalho).status_code == 401
    assert cliente.get("/rota-que-nao-existe", headers=cabecalho).status_code == 401


def test_token_interno_vazio_recusa_tudo(cliente, monkeypatch):
    monkeypatch.setenv("TOKEN_INTERNO", "")
    assert cliente.get("/quebra", headers={"X-Token-Interno": ""}).status_code == 401


def test_log_usa_o_modelo_da_rota_e_nao_leva_dados(cliente, caplog):
    caplog.set_level(logging.INFO)
    r = cliente.post("/eco/maria-silva", json={"texto": "meu cpf e 000"}, headers=TOKEN)
    assert r.status_code == 200
    log_proprio = "\n".join(m.getMessage() for m in caplog.records if m.name == "requisicoes")
    assert "rota=/eco/{nome}" in log_proprio and "status=200" in log_proprio
    for proibido in ("maria-silva", "cpf", "testclient", "token-interno-de-teste"):
        assert proibido not in log_proprio


def test_erro_inesperado_vira_500_sem_detalhes(cliente, caplog):
    r = cliente.get("/quebra", headers=TOKEN)
    assert r.status_code == 500
    assert r.json() == {"erro": "erro interno"}
    assert "RuntimeError" in caplog.text
    assert "sigiloso" not in caplog.text


@pytest.mark.parametrize("texto", ["", "   ", "a\x00b", "a" * (TEXTO_MAXIMO + 1)])
def test_entrada_invalida_da_422_sem_repetir_o_conteudo(cliente, texto):
    r = cliente.post("/eco/x", json={"texto": texto}, headers=TOKEN)
    assert r.status_code == 422
    assert "input" not in r.text


def test_indisponivel_informa_quando_tentar_de_novo():
    r = web.indisponivel("fora", espera=0.2)
    assert r.status_code == 503
    assert r.headers["Retry-After"] == "1"
