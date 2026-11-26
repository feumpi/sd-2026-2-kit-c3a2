"""
Testes ponta a ponta contra o sistema real no docker compose.

  docker compose up --build --wait
  uv run pytest -m e2e

URL_BASE muda o alvo (padrao: http://localhost:8000).
"""
import os
import time
import uuid

import pytest
import requests

pytestmark = pytest.mark.e2e

BASE = os.getenv("URL_BASE", "http://localhost:8000")


@pytest.fixture(scope="module")
def cliente():
    sessao = requests.Session()
    try:
        sessao.get(f"{BASE}/saude", timeout=5).raise_for_status()
    except requests.RequestException:
        pytest.skip(f"sistema fora do ar em {BASE}: rode docker compose up --build --wait")
    return sessao


def esperar(condicao, segundos=60, intervalo=0.5):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        resultado = condicao()
        if resultado:
            return resultado
        time.sleep(intervalo)
    pytest.fail("condicao nao atingida a tempo")


@pytest.fixture(scope="module")
def documento(cliente):
    """Envia um documento unico (o volume pode ter dados de execucoes anteriores)."""
    marca = uuid.uuid4().hex[:12]
    doc = {"texto": f"O protocolo {marca} escolhe um coordenador {marca} por maioria de votos",
           "origem": f"e2e-{marca}"}
    resposta = cliente.post(f"{BASE}/documentos", json=doc, timeout=15)
    assert resposta.status_code == 202, resposta.text
    caminho = resposta.json()["acompanhar"]

    def terminou():
        estado = cliente.get(f"{BASE}{caminho}", timeout=15).json()
        return estado if estado["estado"] != "pendente" else None

    estado = esperar(terminou)
    assert estado["estado"] == "concluida", estado
    return {**doc, "marca": marca, "tarefa": estado}


def test_saude(cliente):
    assert cliente.get(f"{BASE}/saude", timeout=5).json()["status"] == "ok"


def test_predicao_sincrona(cliente):
    resposta = cliente.post(f"{BASE}/predict", timeout=30,
                            json={"texto": "o atendimento foi excelente"})
    assert resposta.status_code == 200
    assert resposta.json()["sentimento"] == "positivo"


def test_documento_passa_pela_fila_e_aparece_na_busca(cliente, documento):
    resposta = cliente.post(f"{BASE}/buscar", timeout=30,
                            json={"pergunta": f"protocolo {documento['marca']}", "top_k": 5})
    assert resposta.status_code == 200
    assert resposta.json()["resultados"][0]["origem"] == documento["origem"]


def test_pergunta_recebe_resposta_fundamentada(cliente, documento):
    resposta = cliente.post(f"{BASE}/perguntar", timeout=30,
                            json={"pergunta": f"como o protocolo {documento['marca']} escolhe?"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert documento["origem"] in corpo["fontes"]
    assert documento["marca"] in corpo["resposta"]


def test_reenviar_o_mesmo_documento_nao_duplica(cliente, documento):
    resposta = cliente.post(f"{BASE}/documentos", timeout=15,
                            json={"texto": documento["texto"], "origem": documento["origem"]})
    caminho = resposta.json()["acompanhar"]
    estado = esperar(lambda: (e := cliente.get(f"{BASE}{caminho}", timeout=15).json())
                     ["estado"] != "pendente" and e)
    assert estado["novo"] == "0"
    assert estado["documento_id"] == documento["tarefa"]["documento_id"]


def test_tarefa_inexistente(cliente):
    assert cliente.get(f"{BASE}/tarefas/nao-existe", timeout=5).status_code == 404
