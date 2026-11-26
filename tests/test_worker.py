"""Testes do worker: fila confiavel, dead-letter, falhas e retencao (sem Redis nem banco)."""
import json
import logging
import threading
import time

import fakeredis
import pytest
import redis
import requests
from fastapi.testclient import TestClient

from comum import contrato
from vetorial.repositorio import BancoIndisponivel, EsquemaAusente, id_documento
from worker import app as servico
from worker import fila, inferencia, worker

DOC = {"texto": "texto sigiloso do documento", "origem": "aula-8"}
ANALISE = {"sentimento": "positivo", "confianca": 0.9, "vetor": [1.0] + [0.0] * 511}


class RepositorioFalso:
    def __init__(self):
        self.documentos = {}
        self.erro = None
        self.expurgos = []
        self.esquemas = 0

    def aplicar_esquema(self):
        self.esquemas += 1

    def gravar(self, texto, origem, sentimento, confianca, vetor):
        if self.erro:
            raise self.erro
        chave = id_documento(texto, origem)
        novo = chave not in self.documentos
        self.documentos.setdefault(chave, texto)
        return chave, novo

    def expurgar(self, dias):
        self.expurgos.append(dias)
        return 0

    def fechar(self):
        pass


class Parada(threading.Event):
    """Registra as esperas sem dormir de verdade."""

    def __init__(self):
        super().__init__()
        self.esperas = []

    def wait(self, timeout=None):
        self.esperas.append(timeout)
        return self.is_set()


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def repo():
    return RepositorioFalso()


@pytest.fixture
def parar():
    return Parada()


@pytest.fixture
def analise(monkeypatch):
    chamadas = []
    monkeypatch.setattr(inferencia, "processar", lambda t: chamadas.append(t) or ANALISE)
    return chamadas


def falhar_com(monkeypatch, erro):
    def processar(texto):
        raise erro
    monkeypatch.setattr(inferencia, "processar", processar)


def erro_http(codigo):
    resposta = requests.Response()
    resposta.status_code = codigo
    return requests.HTTPError(response=resposta)


def rodar(r, repo, parar, vezes=1):
    for _ in range(vezes):
        worker.processar_uma(r, repo, parar, espera=1)


def estado(r, tarefa_id):
    return contrato.consultar_tarefa(r, tarefa_id)


def test_processa_grava_e_conclui(r, repo, parar, analise):
    tarefa_id = contrato.enfileirar(r, DOC)
    rodar(r, repo, parar)
    dados = estado(r, tarefa_id)
    assert dados["estado"] == "concluida" and dados["novo"] == "1"
    assert dados["documento_id"] == id_documento(DOC["texto"], DOC["origem"])
    assert analise == [DOC["texto"]]
    assert r.llen(contrato.FILA) == r.llen(contrato.PROCESSANDO) == 0
    assert DOC["texto"] not in json.dumps(dados)


def test_reentrega_nao_duplica(r, repo, parar, analise):
    contrato.enfileirar(r, DOC)
    segunda = contrato.enfileirar(r, DOC)
    rodar(r, repo, parar, vezes=2)
    assert len(repo.documentos) == 1
    assert estado(r, segunda)["novo"] == "0"


def test_fila_vazia(r, repo, parar):
    assert worker.processar_uma(r, repo, parar, espera=1) is False


@pytest.mark.parametrize("erro", [requests.Timeout(), requests.ConnectionError(),
                                  erro_http(503), erro_http(502), erro_http(429)])
def test_falha_transitoria_nao_gasta_tentativa(r, repo, parar, monkeypatch, erro):
    falhar_com(monkeypatch, erro)
    tarefa_id = contrato.enfileirar(r, DOC)
    rodar(r, repo, parar, vezes=worker.MAX_TENTATIVAS * 4)
    assert r.llen(contrato.DLQ) == 0
    assert r.llen(contrato.FILA) == 1 and r.llen(contrato.PROCESSANDO) == 0
    assert estado(r, tarefa_id)["estado"] == "pendente"
    assert estado(r, tarefa_id)["tentativas"] == "0"
    # espera progressiva, com teto
    assert parar.esperas[0] < parar.esperas[3] <= worker.ESPERA_MAXIMA + worker.BACKOFF_BASE


def test_banco_fora_e_transitorio(r, repo, parar, analise):
    repo.erro = BancoIndisponivel("PoolTimeout")
    tarefa_id = contrato.enfileirar(r, DOC)
    rodar(r, repo, parar, vezes=5)
    assert r.llen(contrato.DLQ) == 0
    repo.erro = None
    rodar(r, repo, parar)
    assert estado(r, tarefa_id)["estado"] == "concluida"


def test_esquema_ausente_e_reaplicado(r, repo, parar, analise):
    repo.erro = EsquemaAusente("UndefinedTable")
    contrato.enfileirar(r, DOC)
    rodar(r, repo, parar)
    assert repo.esquemas == 1 and r.llen(contrato.FILA) == 1


def test_falha_transitoria_velha_demais_vai_para_a_dlq(r, repo, parar, monkeypatch):
    falhar_com(monkeypatch, requests.Timeout())
    tarefa_id = contrato.enfileirar(r, DOC)
    agora = time.time()
    monkeypatch.setattr(worker.time, "time", lambda: agora + worker.IDADE_MAXIMA + 1)
    rodar(r, repo, parar)
    assert r.llen(contrato.DLQ) == 1
    assert estado(r, tarefa_id)["estado"] == "falhou"


@pytest.mark.parametrize("erro", [erro_http(422), erro_http(401), ValueError("x")])
def test_falha_permanente_esgota_tentativas_e_vai_para_a_dlq(r, repo, parar, monkeypatch, erro):
    falhar_com(monkeypatch, erro)
    tarefa_id = contrato.enfileirar(r, DOC)
    rodar(r, repo, parar, vezes=worker.MAX_TENTATIVAS - 1)
    assert r.llen(contrato.DLQ) == 0
    assert estado(r, tarefa_id)["tentativas"] == str(worker.MAX_TENTATIVAS - 1)
    rodar(r, repo, parar)
    assert r.llen(contrato.DLQ) == 1
    assert r.llen(contrato.FILA) == r.llen(contrato.PROCESSANDO) == 0
    assert estado(r, tarefa_id)["estado"] == "falhou"


@pytest.mark.parametrize("mensagem", [
    "isto nao e json", "[]", json.dumps({"id": "x"}),
    json.dumps({"id": "x", "documento": {"texto": "", "origem": "o"}, "criada_em": 1}),
])
def test_mensagem_malformada_vai_direto_para_a_dlq(r, repo, parar, mensagem):
    r.lpush(contrato.FILA, mensagem)
    rodar(r, repo, parar)
    assert r.llen(contrato.DLQ) == 1
    assert r.llen(contrato.PROCESSANDO) == 0


def test_tarefa_interrompida_volta_para_a_fila(r, repo, parar, analise):
    tarefa_id = contrato.enfileirar(r, DOC)
    fila.retirar(r, 1)  # worker caiu depois de pegar a mensagem
    assert fila.recuperar_pendentes(r) == 1
    rodar(r, repo, parar)
    assert estado(r, tarefa_id)["estado"] == "concluida"


def test_dlq_expira_e_e_expurgada(r):
    vencida = {"mensagem": "velha", "motivo": "teste",
               "em": time.time() - fila.DLQ_RETENCAO - 10}
    r.lpush(contrato.DLQ, json.dumps(vencida))
    fila.descartar(r, "nova", None, "teste")
    assert 0 < r.ttl(contrato.DLQ) <= fila.DLQ_RETENCAO
    assert fila.expurgar_dlq(r) == 1
    assert json.loads(r.lindex(contrato.DLQ, 0))["mensagem"] == "nova"


def test_consumidor_prepara_o_banco_e_expurga_na_subida(r, repo, monkeypatch):
    parar = Parada()
    monkeypatch.setattr(worker, "processar_uma", lambda *a: parar.set())
    worker.consumir(r, repo, parar)
    assert repo.esquemas == 1
    assert repo.expurgos == [worker.RETENCAO_DIAS]


def test_consumidor_sobrevive_ao_redis_fora(repo, monkeypatch):
    parar = Parada()
    voltas = []

    def passo(*a):
        voltas.append(1)
        if len(voltas) == 1:
            raise redis.ConnectionError("caiu")
        parar.set()

    monkeypatch.setattr(worker, "processar_uma", passo)
    worker.consumir(fakeredis.FakeRedis(decode_responses=True), repo, parar)
    assert len(voltas) == 2 and parar.esperas == [worker.PAUSA_FALHA]


def test_logs_nao_levam_o_texto(r, repo, parar, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    falhar_com(monkeypatch, ValueError(DOC["texto"]))
    tarefa_id = contrato.enfileirar(r, DOC)
    rodar(r, repo, parar, vezes=worker.MAX_TENTATIVAS)
    assert "sigiloso" not in caplog.text
    assert "sigiloso" not in json.dumps(estado(r, tarefa_id))


def test_cliente_da_inferencia_envia_token_e_tempo_limite(monkeypatch):
    chamada = {}

    def post(url, **argumentos):
        chamada.update(argumentos, url=url)
        resposta = requests.Response()
        resposta.status_code = 200
        resposta._content = json.dumps(ANALISE).encode()
        return resposta

    monkeypatch.setattr(inferencia.requests, "post", post)
    assert inferencia.processar("oi")["sentimento"] == "positivo"
    assert chamada["url"].endswith("/processar")
    assert chamada["headers"]["X-Token-Interno"] == "token-interno-de-teste"
    assert all(t > 0 for t in chamada["timeout"])


def test_saude_acompanha_a_thread(monkeypatch, repo):
    liberar = threading.Event()
    monkeypatch.setattr(servico, "consumir", lambda r, repo, parar: liberar.wait(5))
    monkeypatch.setattr(servico, "repositorio", repo)
    with TestClient(servico.app) as cliente:
        assert cliente.get("/saude").status_code == 200
        assert cliente.get("/qualquer").status_code == 401
        liberar.set()
        servico.app.state.consumidor.join(2)
        r = cliente.get("/saude")
    assert r.status_code == 503 and r.json()["consumidor_vivo"] is False
