"""Testes da TAREFA 1: login, token JWT e rotas protegidas."""
import logging
import time

import fakeredis
import jwt
import pytest
from fastapi.testclient import TestClient

from gateway import app as gateway
from gateway import autenticacao

SEGREDO = "segredo-de-teste-com-mais-de-32-bytes!!"
LOGIN = {"usuario": "usuario-teste", "senha": "senha-de-teste"}
PROTEGIDAS = [("post", "/predict"), ("post", "/documentos"), ("get", "/tarefas/x"),
              ("post", "/buscar"), ("post", "/perguntar")]


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(gateway, "redis_cliente", fakeredis.FakeRedis(decode_responses=True))
    return TestClient(gateway.app)


def pedir(cliente, cabecalho=None):
    cabecalhos = {"Authorization": cabecalho} if cabecalho else {}
    return cliente.get("/tarefas/nao-existe", headers=cabecalhos)


def token(**dados):
    base = {"sub": "usuario-teste", "exp": int(time.time()) + 60}
    base.update(dados)
    return jwt.encode({k: v for k, v in base.items() if v is not None}, SEGREDO, "HS256")


def test_login_emite_token_com_prazo_que_abre_as_rotas(cliente):
    resposta = cliente.post("/login", json=LOGIN)
    assert resposta.status_code == 200
    corpo = resposta.json()
    dados = jwt.decode(corpo["token"], SEGREDO, algorithms=["HS256"])
    assert dados["sub"] == "usuario-teste"
    assert dados["exp"] - dados["iat"] == corpo["expira_em_segundos"]
    assert pedir(cliente, f"Bearer {corpo['token']}").status_code == 404  # passou da porta


@pytest.mark.parametrize("credenciais", [
    {"usuario": "usuario-teste", "senha": "errada"},
    {"usuario": "outro", "senha": "senha-de-teste"},
    {"usuario": "usuário-çã", "senha": "senha-ção"},
])
def test_login_errado_da_401(cliente, credenciais):
    assert cliente.post("/login", json=credenciais).status_code == 401


@pytest.mark.parametrize("variavel", ["USUARIO_DEMO", "SENHA_DEMO"])
def test_sem_credenciais_configuradas_todo_login_e_recusado(cliente, monkeypatch, variavel):
    monkeypatch.setenv(variavel, "")
    assert cliente.post("/login", json=LOGIN).status_code == 401


@pytest.mark.parametrize("metodo, rota", PROTEGIDAS)
def test_toda_rota_de_negocio_exige_token(cliente, metodo, rota):
    resposta = getattr(cliente, metodo)(rota)
    assert resposta.status_code == 401
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("rota", ["/saude", "/docs", "/openapi.json"])
def test_rotas_abertas(cliente, rota):
    assert cliente.get(rota).status_code == 200


@pytest.mark.parametrize("cabecalho", [
    "Bearer", "Bearer nao-e-um-jwt", "Basic dXN1YXJpbzpzZW5oYQ==",
    "Bearer " + jwt.encode({"sub": "a", "exp": 9999999999},
                           "outro-segredo-tambem-com-32-bytes-ou-mais", "HS256"),
    "Bearer " + jwt.encode({"sub": "a", "exp": 9999999999}, "", "none"),
    "Bearer " + token(exp=int(time.time()) - 10),
    "Bearer " + token(exp=None),
    "Bearer " + token(sub=None),
])
def test_token_invalido_ou_expirado_da_401(cliente, cabecalho):
    assert pedir(cliente, cabecalho).status_code == 401


def test_documentacao_tem_o_botao_authorize(cliente):
    esquema = cliente.get("/openapi.json").json()
    assert "HTTPBearer" in esquema["components"]["securitySchemes"]
    assert esquema["paths"]["/predict"]["post"]["security"]
    assert "security" not in esquema["paths"]["/login"]["post"]


@pytest.mark.parametrize("valor", ["", "curto"])
def test_segredo_fraco_impede_a_subida(monkeypatch, valor):
    monkeypatch.setenv("JWT_SEGREDO", valor)
    with pytest.raises(RuntimeError):
        autenticacao.segredo()
    with pytest.raises(RuntimeError), TestClient(gateway.app):
        pass


def test_nada_do_login_vai_para_o_log(cliente, caplog):
    caplog.set_level(logging.DEBUG)
    corpo = cliente.post("/login", json=LOGIN).json()
    cliente.post("/login", json={"usuario": "intruso", "senha": "chute"})
    pedir(cliente, f"Bearer {corpo['token']}")
    for proibido in ("usuario-teste", "senha-de-teste", "intruso", "chute", corpo["token"]):
        assert proibido not in caplog.text
