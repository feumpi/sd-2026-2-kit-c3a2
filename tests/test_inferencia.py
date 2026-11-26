"""Testes do servico de inferencia, com o banco substituido (sem rede e sem Docker)."""
import logging

import pytest
from fastapi.testclient import TestClient

from inferencia import app as inferencia
from inferencia import llm, modelo
from inferencia.embeddings import DIMENSAO, Vetorizador
from vetorial.repositorio import DIMENSAO as DIMENSAO_BANCO
from vetorial.repositorio import BancoIndisponivel, EsquemaAusente

TOKEN = {"X-Token-Interno": "token-interno-de-teste"}
TRECHOS = [
    {"origem": "cap", "texto": "O teorema CAP trata de particao.", "sentimento": "positivo",
     "score": 0.6123456},
    {"origem": "raft", "texto": "Raft elege um lider.", "sentimento": "positivo", "score": 0.0},
]


class RepositorioFalso:
    def __init__(self, resultado):
        self.resultado = resultado
        self.chamadas = []

    def buscar(self, vetor, top_k):
        self.chamadas.append((len(vetor), top_k))
        if isinstance(self.resultado, Exception):
            raise self.resultado
        return self.resultado

    def fechar(self):
        pass


@pytest.fixture
def repo(monkeypatch):
    falso = RepositorioFalso(TRECHOS)
    monkeypatch.setattr(inferencia, "repositorio", falso)
    return falso


@pytest.fixture
def cliente(repo, monkeypatch, tmp_path):
    monkeypatch.setattr(modelo, "CAMINHO", str(tmp_path / "modelo.joblib"))
    with TestClient(inferencia.app, headers=TOKEN) as c:
        yield c


def test_vetor_tem_dimensao_fixa_igual_a_do_banco():
    v = Vetorizador()
    assert DIMENSAO == DIMENSAO_BANCO == 512
    assert len(v.vetorizar("um texto")) == len(v.vetorizar("outro texto bem maior " * 50)) == 512
    assert v.vetorizar("mesmo texto") == v.vetorizar("mesmo texto")
    assert not any(v.vetorizar("! ?"))


@pytest.mark.parametrize("rota", ["/predict", "/processar", "/buscar", "/perguntar"])
def test_sem_token_interno_da_401(cliente, rota):
    r = cliente.post(rota, json={}, headers={"X-Token-Interno": "errado"})
    assert r.status_code == 401


def test_saude_sem_token(cliente):
    corpo = cliente.get("/saude", headers={"X-Token-Interno": ""}).json()
    assert corpo["modelo_carregado"] is True
    assert corpo["llm"] == "simulado"


def test_documentacao_nao_e_exposta(cliente):
    assert cliente.get("/docs").status_code == 404
    assert cliente.get("/openapi.json").status_code == 404


def test_predict_segue_o_contrato_do_kit(cliente):
    corpo = cliente.post("/predict", json={"texto": "o atendimento foi excelente"}).json()
    assert corpo["sentimento"] == "positivo"
    assert set(corpo) == {"texto", "sentimento", "confianca"}


def test_processar_devolve_sentimento_e_vetor(cliente):
    corpo = cliente.post("/processar", json={"texto": "pessimo atendimento, ninguem resolve nada"}).json()
    assert corpo["sentimento"] == "negativo"
    assert len(corpo["vetor"]) == 512
    assert "texto" not in corpo


def test_processar_recusa_texto_sem_palavras(cliente):
    assert cliente.post("/processar", json={"texto": "!!!"}).status_code == 422


def test_buscar_descarta_trechos_sem_semelhanca(cliente, repo):
    corpo = cliente.post("/buscar", json={"pergunta": "teorema CAP", "top_k": 2}).json()
    assert [r["origem"] for r in corpo["resultados"]] == ["cap"]
    assert corpo["resultados"][0]["score"] == 0.6123
    assert repo.chamadas == [(512, 2)]


def test_buscar_sem_palavras_nem_consulta_o_banco(cliente, repo):
    assert cliente.post("/buscar", json={"pergunta": "?"}).json() == {"resultados": []}
    assert repo.chamadas == []


@pytest.mark.parametrize("top_k", [0, 21])
def test_top_k_fora_do_intervalo_da_422(cliente, top_k):
    assert cliente.post("/buscar", json={"pergunta": "x y", "top_k": top_k}).status_code == 422


def test_esquema_ainda_ausente_devolve_vazio(cliente, repo):
    repo.resultado = EsquemaAusente("UndefinedTable")
    assert cliente.post("/buscar", json={"pergunta": "teorema"}).json() == {"resultados": []}


@pytest.mark.parametrize("rota", ["/buscar", "/perguntar"])
def test_banco_fora_do_ar_da_503_degradado(cliente, repo, rota):
    repo.resultado = BancoIndisponivel("PoolTimeout")
    r = cliente.post(rota, json={"pergunta": "teorema CAP"})
    assert r.status_code == 503
    assert r.json()["degradado"] is True
    assert int(r.headers["Retry-After"]) >= 1


def test_perguntar_responde_em_modo_simulado_com_fontes(cliente):
    corpo = cliente.post("/perguntar", json={"pergunta": "o que e o teorema CAP?"}).json()
    assert "MODO SIMULADO" in corpo["resposta"]
    assert corpo["fontes"] == ["cap"]


def test_sem_base_nao_chama_o_llm(cliente, repo, monkeypatch):
    repo.resultado = []
    monkeypatch.setattr(llm, "gerar", lambda *a, **k: pytest.fail("nao deveria chamar"))
    corpo = cliente.post("/perguntar", json={"pergunta": "assunto inexistente"}).json()
    assert corpo == {"resposta": inferencia.SEM_BASE, "contexto": [], "fontes": []}


def test_llm_com_erro_degrada_com_trechos(cliente, monkeypatch):
    def quebra(*a, **k):
        raise OSError("fora")
    monkeypatch.setattr(llm, "gerar", quebra)
    r = cliente.post("/perguntar", json={"pergunta": "teorema CAP"})
    assert r.status_code == 503
    assert r.json()["fontes"] == ["cap"] and r.json()["degradado"] is True


def test_logs_nao_levam_texto_nem_pergunta(cliente, caplog):
    caplog.set_level(logging.DEBUG)
    cliente.post("/predict", json={"texto": "segredo alfa excelente"})
    cliente.post("/perguntar", json={"pergunta": "segredo beta teorema"})
    assert "segredo" not in caplog.text
