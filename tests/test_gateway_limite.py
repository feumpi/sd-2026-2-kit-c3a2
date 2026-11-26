"""Testes da TAREFA 2: limite de requisicoes por cliente e por minuto."""
import logging
from types import SimpleNamespace

import fakeredis
import pytest
import redis
from fastapi.testclient import TestClient
from starlette.requests import Request

from gateway import app as gateway
from gateway import autenticacao, limite


class Relogio:
    def __init__(self):
        self.agora = 6000.0 + 15  # 15 s depois do inicio de uma janela

    def __call__(self):
        return self.agora


@pytest.fixture
def relogio(monkeypatch):
    r = Relogio()
    # troca so o relogio do limite: o JWT continua no tempo real
    monkeypatch.setattr(limite, "time", SimpleNamespace(time=r))
    return r


@pytest.fixture
def r(monkeypatch):
    falso = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(gateway, "redis_cliente", falso)
    monkeypatch.setattr(limite, "LIMITE", 3)
    return falso


def cliente(usuario="usuario-teste", ip="203.0.113.7") -> TestClient:
    token = autenticacao.emitir_token(usuario)
    return TestClient(gateway.app, client=(ip, 5000),
                      headers={"Authorization": f"Bearer {token}"})


def consultar(c):
    return c.get("/tarefas/nao-existe")


def test_429_ao_estourar_com_retry_after(r, relogio):
    c = cliente()
    assert [consultar(c).status_code for _ in range(3)] == [404, 404, 404]
    resposta = consultar(c)
    assert resposta.status_code == 429
    assert resposta.headers["Retry-After"] == "45"


def test_libera_na_janela_seguinte(r, relogio):
    c = cliente()
    for _ in range(4):
        consultar(c)
    relogio.agora += 45
    assert consultar(c).status_code == 404


def test_cada_usuario_tem_a_propria_cota(r, relogio):
    for _ in range(4):
        consultar(cliente("a"))
    assert consultar(cliente("a")).status_code == 429
    assert consultar(cliente("b")).status_code == 404


def test_login_e_limitado_por_endereco(r, relogio):
    errado = {"usuario": "x", "senha": "y"}
    a, b = cliente(ip="198.51.100.1"), cliente(ip="198.51.100.2")
    assert [a.post("/login", json=errado).status_code for _ in range(4)] == [401, 401, 401, 429]
    # nem a senha certa passa depois de estourar; outro endereco nao e afetado
    certo = {"usuario": "usuario-teste", "senha": "senha-de-teste"}
    assert a.post("/login", json=certo).status_code == 429
    assert b.post("/login", json=certo).status_code == 200


def test_chaves_nao_guardam_ip_nem_usuario_e_expiram(r, relogio):
    cliente("maria", "198.51.100.9").post("/login", json={"usuario": "maria", "senha": "x"})
    consultar(cliente("maria"))
    chaves = r.keys("limite:*")
    assert len(chaves) == 2
    for nome in chaves:
        assert "maria" not in nome and "198.51.100.9" not in nome
        assert 0 < r.ttl(nome) <= 60


@pytest.mark.parametrize("rota", ["/saude", "/docs", "/openapi.json", "/"])
def test_rotas_abertas_nao_sao_limitadas(r, relogio, rota):
    c = cliente()
    assert {c.get(rota).status_code for _ in range(8)} == {200}


def test_sem_token_da_401_e_nao_conta(r, relogio):
    anonimo = TestClient(gateway.app)
    assert {anonimo.get("/tarefas/x").status_code for _ in range(6)} == {401}
    assert r.keys("limite:*") == []


def test_redis_fora_do_ar_libera_e_avisa(monkeypatch, caplog):
    class RedisFora:
        def __getattr__(self, nome):
            def falha(*a, **k):
                raise redis.ConnectionError("caiu")
            return falha

    monkeypatch.setattr(gateway, "redis_cliente", RedisFora())
    caplog.set_level(logging.WARNING)
    resposta = TestClient(gateway.app).post(
        "/login", json={"usuario": "usuario-teste", "senha": "senha-de-teste"})
    assert resposta.status_code == 200
    assert "rate limit indisponivel" in caplog.text


def requisicao(cabecalhos: dict) -> Request:
    return Request({"type": "http", "client": ("10.0.0.1", 1),
                    "headers": [(k.lower().encode(), v.encode()) for k, v in cabecalhos.items()]})


def test_por_padrao_ignora_cabecalhos_que_o_cliente_pode_forjar(monkeypatch):
    monkeypatch.setattr(limite, "CABECALHO_IP", "")
    monkeypatch.setattr(limite, "PROXIES_CONFIAVEIS", 0)
    pedido = requisicao({"X-Forwarded-For": "1.1.1.1", "CF-Connecting-IP": "2.2.2.2"})
    assert limite.endereco_do_cliente(pedido) == "10.0.0.1"


def test_cabecalho_do_proxy_tem_prioridade(monkeypatch):
    monkeypatch.setattr(limite, "CABECALHO_IP", "CF-Connecting-IP")
    pedido = requisicao({"X-Forwarded-For": "1.1.1.1", "CF-Connecting-IP": "2.2.2.2"})
    assert limite.endereco_do_cliente(pedido) == "2.2.2.2"


@pytest.mark.parametrize("proxies, esperado", [(1, "4.4.4.4"), (2, "3.3.3.3"), (9, "10.0.0.1")])
def test_x_forwarded_for_e_lido_da_direita(monkeypatch, proxies, esperado):
    monkeypatch.setattr(limite, "CABECALHO_IP", "")
    monkeypatch.setattr(limite, "PROXIES_CONFIAVEIS", proxies)
    pedido = requisicao({"X-Forwarded-For": "forjado, 3.3.3.3, 4.4.4.4"})
    assert limite.endereco_do_cliente(pedido) == esperado
