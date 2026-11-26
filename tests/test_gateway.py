"""Testes de roteamento do gateway, com Redis falso e chamadas HTTP substituidas."""
import json
import logging

import fakeredis
import pytest
import redis
import requests
from fastapi.testclient import TestClient

from comum import contrato
from gateway import app as gateway
from gateway import autenticacao, despertar, inferencia


def resposta_http(codigo, corpo=None, cabecalhos=None):
    resposta = requests.Response()
    resposta.status_code = codigo
    resposta._content = b"<html>" if corpo is None else json.dumps(corpo).encode()
    resposta.headers.update(cabecalhos or {})
    return resposta


@pytest.fixture
def r(monkeypatch):
    falso = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(gateway, "redis_cliente", falso)
    return falso


@pytest.fixture
def remoto(monkeypatch):
    """Substitui a inferencia: programe `respostas` e confira `chamadas`."""
    estado = {"respostas": [], "chamadas": []}

    def post(url, **argumentos):
        estado["chamadas"].append((url, argumentos))
        item = estado["respostas"].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(inferencia.requests, "post", post)
    return estado


def autorizado() -> TestClient:
    """Cliente com um token valido."""
    token = autenticacao.emitir_token("usuario-teste")
    return TestClient(gateway.app, headers={"Authorization": f"Bearer {token}"})


@pytest.fixture
def cliente(r):
    return autorizado()


def test_raiz_redireciona_para_a_documentacao(cliente):
    r = cliente.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/docs"


def test_saude_nao_depende_de_ninguem(monkeypatch):
    monkeypatch.setattr(gateway, "redis_cliente", None)
    assert TestClient(gateway.app).get("/saude").status_code == 200


@pytest.mark.parametrize("rota, corpo", [
    ("/predict", {"texto": "bom"}),
    ("/buscar", {"pergunta": "cap", "top_k": 2}),
    ("/perguntar", {"pergunta": "cap"}),
])
def test_rotas_sincronas_sao_repassadas(cliente, remoto, rota, corpo):
    remoto["respostas"].append(resposta_http(200, {"ok": rota}))
    r = cliente.post(rota, json=corpo)
    assert r.status_code == 200 and r.json() == {"ok": rota}
    url, argumentos = remoto["chamadas"][0]
    assert url == f"{inferencia.URL_INFERENCIA}{rota}"
    assert argumentos["headers"]["X-Token-Interno"] == "token-interno-de-teste"
    assert all(t > 0 for t in argumentos["timeout"])


@pytest.mark.parametrize("resposta", [
    requests.ConnectionError("http://interno:8001 recusou"),
    requests.Timeout("lento"),
    resposta_http(500, {"erro": "detalhe interno"}),
    resposta_http(401, {"erro": "token interno invalido"}),
    resposta_http(502),
])
def test_falha_da_inferencia_vira_503_generico(cliente, remoto, resposta):
    remoto["respostas"].append(resposta)
    r = cliente.post("/predict", json={"texto": "bom"})
    assert r.status_code == 503
    assert r.json() == {"erro": inferencia.INDISPONIVEL}
    assert int(r.headers["Retry-After"]) >= 1


def test_resposta_degradada_e_repassada_sem_trocar_o_corpo(cliente, remoto):
    corpo = {"erro": "LLM indisponivel", "degradado": True, "fontes": ["a"]}
    remoto["respostas"].append(resposta_http(503, corpo, {"Retry-After": "12"}))
    r = cliente.post("/perguntar", json={"pergunta": "cap"})
    assert r.status_code == 503 and r.json() == corpo
    assert r.headers["Retry-After"] == "12"


@pytest.mark.parametrize("rota, corpo", [
    ("/predict", {"texto": ""}), ("/predict", {}),
    ("/documentos", {"texto": "  "}), ("/buscar", {"pergunta": "x", "top_k": 50}),
])
def test_entrada_invalida_nem_sai_do_gateway(cliente, remoto, rota, corpo):
    assert cliente.post(rota, json=corpo).status_code == 422
    assert remoto["chamadas"] == []


def test_documento_e_enfileirado_com_202(cliente, r):
    resposta = cliente.post("/documentos", json={"texto": "doc", "origem": "aula"})
    assert resposta.status_code == 202
    corpo = resposta.json()
    mensagem = json.loads(r.lindex(contrato.FILA, 0))
    assert mensagem["id"] == corpo["id"]
    assert mensagem["documento"] == {"texto": "doc", "origem": "aula"}
    consulta = cliente.get(corpo["acompanhar"]).json()
    assert consulta["estado"] == "pendente" and consulta["id"] == corpo["id"]


def test_tarefa_inexistente_da_404(cliente):
    assert cliente.get("/tarefas/nao-existe").status_code == 404


@pytest.mark.parametrize("metodo, rota, corpo", [
    ("post", "/documentos", {"texto": "doc"}), ("get", "/tarefas/abc", None),
])
def test_fila_fora_do_ar_da_503(monkeypatch, metodo, rota, corpo):
    class RedisFora:
        def __getattr__(self, nome):
            def falha(*a, **k):
                raise redis.ConnectionError("redis://:senha@host caiu")
            return falha

    monkeypatch.setattr(gateway, "redis_cliente", RedisFora())
    argumentos = {"json": corpo} if corpo else {}
    r = getattr(autorizado(), metodo)(rota, **argumentos)
    assert r.status_code == 503 and "senha" not in r.text
    assert "Retry-After" in r.headers


def test_enfileirar_e_consultar_pendente_despertam_o_worker(cliente, monkeypatch):
    chamadas = []
    monkeypatch.setattr(gateway, "despertar", lambda *u: chamadas.append(u))
    corpo = cliente.post("/documentos", json={"texto": "doc"}).json()
    cliente.get(corpo["acompanhar"])
    assert chamadas == [(gateway.URL_WORKER,), (gateway.URL_WORKER,)]


def test_despertar_nao_repete_dentro_do_intervalo(monkeypatch):
    urls = []

    class Linha:
        def __init__(self, target, args, daemon):
            self.args = args

        def start(self):
            urls.append(self.args[0])

    monkeypatch.setattr(despertar, "ATIVO", True)
    monkeypatch.setattr(despertar, "_ultimo", {})
    monkeypatch.setattr(despertar.threading, "Thread", Linha)
    despertar.despertar("http://a", "http://b")
    despertar.despertar("http://a")
    assert urls == ["http://a", "http://b"]


def test_logs_nao_levam_o_texto(cliente, remoto, caplog):
    caplog.set_level(logging.DEBUG)
    remoto["respostas"].append(requests.ConnectionError("segredo na url"))
    cliente.post("/predict", json={"texto": "segredo do cliente"})
    cliente.post("/documentos", json={"texto": "segredo do documento"})
    assert "segredo" not in caplog.text
