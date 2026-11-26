"""TAREFA 6: disjuntores, retentativas e tempo-limite nas tres chamadas remotas."""
# pyright: reportOptionalSubscript=false
import json
import threading

import fakeredis
import pytest
import requests
from fastapi.testclient import TestClient

from comum import contrato, resiliencia
from comum.circuit_breaker import CircuitoAberto
from comum.resiliencia import com_retentativa
from gateway import app as gateway
from gateway import autenticacao
from gateway import inferencia as do_gateway
from inferencia import app as servico
from inferencia import llm
from worker import inferencia as do_worker
from worker import worker

DEGRADADA = {"erro": "armazenamento vetorial indisponivel", "degradado": True}


def resposta_http(codigo, corpo=None):
    resposta = requests.Response()
    resposta.status_code = codigo
    resposta._content = json.dumps(corpo or {}).encode()
    return resposta


class Remoto:
    """Substitui requests.post: consome a lista; o ultimo item se repete."""

    def __init__(self, *itens):
        self.itens = list(itens)
        self.tempos = []

    def __call__(self, url, **argumentos):
        self.tempos.append(argumentos["timeout"])
        item = self.itens.pop(0) if len(self.itens) > 1 else self.itens[0]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def remoto(monkeypatch):
    def instalar(*itens):
        falso = Remoto(*itens)
        monkeypatch.setattr(requests, "post", falso)
        return falso

    return instalar


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(gateway, "redis_cliente", fakeredis.FakeRedis(decode_responses=True))
    token = autenticacao.emitir_token("usuario-teste")
    return TestClient(gateway.app, headers={"Authorization": f"Bearer {token}"})


def predizer(cliente):
    return cliente.post("/predict", json={"texto": "bom"})


# --- gateway -> inferencia

def test_gateway_supera_falha_passageira(cliente, remoto):
    falso = remoto(requests.ConnectionError(), resposta_http(502), resposta_http(200, {"a": 1}))
    assert predizer(cliente).json() == {"a": 1}
    assert len(falso.tempos) == 3
    assert do_gateway.disjuntor.falhas == 0


def test_gateway_abre_o_disjuntor_e_recusa_na_hora(cliente, remoto):
    falso = remoto(requests.ConnectionError())
    for _ in range(3):
        assert predizer(cliente).status_code == 503
    assert len(falso.tempos) == 9  # 3 sequencias de 3 tentativas = 3 falhas
    assert do_gateway.disjuntor.estado == "aberto"
    resposta = predizer(cliente)
    assert resposta.status_code == 503 and len(falso.tempos) == 9
    assert 1 <= int(resposta.headers["Retry-After"]) <= 20
    assert cliente.get("/saude").json()["disjuntores"] == {"inferencia": "aberto"}


@pytest.mark.parametrize("resposta", [
    resposta_http(422, {"erro": "texto invalido"}), resposta_http(503, DEGRADADA),
])
def test_gateway_nao_conta_4xx_nem_resposta_degradada(cliente, remoto, resposta):
    falso = remoto(resposta)
    for _ in range(6):
        assert predizer(cliente).status_code == resposta.status_code
    assert len(falso.tempos) == 6  # sem retentativa
    assert do_gateway.disjuntor.estado == "fechado"


def test_gateway_encurta_o_tempo_limite_para_caber_no_prazo(cliente, remoto, monkeypatch):
    agora = [0.0]
    monkeypatch.setattr(resiliencia.time, "monotonic", lambda: agora[0])
    monkeypatch.setattr(do_gateway, "TIMEOUT", 90.0)
    monkeypatch.setattr(do_gateway, "PRAZO_TOTAL", 120.0)
    tempos = []

    def lento(url, **argumentos):
        limite = argumentos["timeout"][1]
        tempos.append(limite)
        agora[0] += limite  # a tentativa consome todo o tempo-limite
        raise requests.Timeout()

    monkeypatch.setattr(requests, "post", lento)
    assert predizer(cliente).status_code == 503
    assert tempos == [90.0, 30.0]
    assert sum(tempos) <= 120


# --- worker -> inferencia

def test_cliente_do_worker_retenta_5xx_e_conta_uma_falha(remoto):
    falso = remoto(resposta_http(503))
    with pytest.raises(requests.HTTPError):
        do_worker.processar("x")
    assert len(falso.tempos) == 3 and do_worker.disjuntor.falhas == 1


def test_4xx_nao_abre_o_disjuntor_do_worker(remoto):
    falso = remoto(resposta_http(422))
    for _ in range(5):
        with pytest.raises(requests.HTTPError):
            do_worker.processar("x")
    assert len(falso.tempos) == 5 and do_worker.disjuntor.estado == "fechado"


def test_circuito_aberto_nao_manda_a_tarefa_para_a_dlq(remoto, monkeypatch):
    r = fakeredis.FakeRedis(decode_responses=True)
    falso = remoto(requests.ConnectionError())
    tarefa_id = contrato.enfileirar(r, {"texto": "doc", "origem": "o"})
    esperas = []

    class Parada(threading.Event):
        def wait(self, timeout=None):
            esperas.append(timeout)
            return False

    for _ in range(8):
        worker.processar_uma(r, repositorio=None, parar=Parada(), espera=1)
    assert do_worker.disjuntor.estado == "aberto"
    assert len(falso.tempos) == 9  # depois de abrir, ninguem mais chama
    assert r.llen(contrato.DLQ) == 0 and r.llen(contrato.FILA) == 1
    assert contrato.consultar_tarefa(r, tarefa_id)["tentativas"] == "0"
    assert 1 <= esperas[-1] <= 20  # espera o que o disjuntor pede
    with pytest.raises(CircuitoAberto):
        do_worker.processar("x")


# --- inferencia -> LLM

TRECHOS = [{"origem": "cap", "texto": "teorema CAP", "sentimento": "positivo", "score": 0.5}]


@pytest.fixture
def perguntar(monkeypatch):
    monkeypatch.setattr(llm, "API_KEY", "chave-de-teste")
    monkeypatch.setattr(servico, "recuperar", lambda consulta: TRECHOS)
    cliente = TestClient(servico.app, headers={"X-Token-Interno": "token-interno-de-teste"})
    return lambda: cliente.post("/perguntar", json={"pergunta": "o que e o CAP?"})


def do_llm(texto):
    return resposta_http(200, {"choices": [{"message": {"content": texto}}]})


def test_llm_e_retentado_ate_responder(perguntar, remoto):
    falso = remoto(requests.Timeout(), resposta_http(502), do_llm("resposta do LLM"))
    assert perguntar().json()["resposta"] == "resposta do LLM"
    assert len(falso.tempos) == 3
    assert all(0 < t <= llm.TIMEOUT for t in falso.tempos)


def test_llm_fora_abre_o_disjuntor_e_degrada_com_os_trechos(perguntar, remoto):
    falso = remoto(requests.ConnectionError())
    for _ in range(4):
        resposta = perguntar()
        assert resposta.status_code == 503
        assert resposta.json()["fontes"] == ["cap"] and resposta.json()["degradado"]
    assert len(falso.tempos) == 9
    assert servico.disjuntor_llm.estado == "aberto"


def test_prazo_do_llm_cabe_no_tempo_limite_do_gateway():
    assert servico.LLM_PRAZO_TOTAL < do_gateway.TIMEOUT


def test_retentativa_sem_tempo_limite_nao_passa_o_argumento():
    assert com_retentativa(lambda: "ok")() == "ok"
