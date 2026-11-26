"""
Testes ponta a ponta contra o sistema real no docker compose.

  docker compose up --build --wait
  uv run pytest -m e2e

Contra o ambiente publicado:
  URL_BASE=https://... E2E_CREDENCIAIS=caminho/do/arquivo uv run pytest -m e2e

O arquivo de credenciais tem linhas USUARIO_DEMO=... e SENHA_DEMO=... e fica fora do
repositorio. Sem ele valem E2E_USUARIO/E2E_SENHA ou os padroes do compose local.
"""
import json
import os
import subprocess
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import requests

pytestmark = pytest.mark.e2e

BASE = os.getenv("URL_BASE", "http://localhost:8000").rstrip("/")
LOCAL = "localhost" in BASE or "127.0.0.1" in BASE
# na nuvem os servicos podem estar dormindo: o primeiro acesso leva mais de um minuto
ESPERA = 60 if LOCAL else 240
TEMPO_LIMITE = 30 if LOCAL else 150
# intervalo que nao estoura o limite de requisicoes por minuto
INTERVALO = 2
RAIZ = Path(__file__).resolve().parent.parent


def credenciais() -> dict:
    arquivo = os.getenv("E2E_CREDENCIAIS")
    if arquivo:
        linhas = Path(arquivo).expanduser().read_text(encoding="utf-8").splitlines()
        valores = dict(linha.split("=", 1) for linha in linhas if "=" in linha)
        return {"usuario": valores["USUARIO_DEMO"], "senha": valores["SENHA_DEMO"]}
    return {"usuario": os.getenv("E2E_USUARIO", "aluno"),
            "senha": os.getenv("E2E_SENHA", "senha-local-do-compose")}


@pytest.fixture(scope="module")
def anonimo():
    sessao = requests.Session()
    try:
        sessao.get(f"{BASE}/saude", timeout=TEMPO_LIMITE if not LOCAL else 5).raise_for_status()
    except requests.RequestException:
        pytest.skip(f"sistema fora do ar em {BASE}: rode docker compose up --build --wait")
    return sessao


@pytest.fixture(scope="module")
def cliente(anonimo):
    resposta = requests.post(f"{BASE}/login", json=credenciais(), timeout=TEMPO_LIMITE)
    assert resposta.status_code == 200, f"login recusado: {resposta.status_code}"
    sessao = requests.Session()
    sessao.headers["Authorization"] = f"Bearer {resposta.json()['token']}"
    return sessao


def esperar(condicao, segundos=ESPERA, intervalo=INTERVALO):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        resultado = condicao()
        if resultado:
            return resultado
        time.sleep(intervalo)
    pytest.fail("condicao nao atingida a tempo")


def terminada(cliente, caminho):
    """Estado da tarefa se ja saiu de pendente; respeita o 429."""
    resposta = cliente.get(f"{BASE}{caminho}", timeout=TEMPO_LIMITE)
    if resposta.status_code == 429:
        time.sleep(int(resposta.headers.get("Retry-After", "5")))
        return None
    estado = resposta.json()
    return estado if estado.get("estado") in ("concluida", "falhou") else None


@pytest.fixture(scope="module")
def documento(cliente):
    """Envia um documento unico (o volume pode ter dados de execucoes anteriores)."""
    marca = uuid.uuid4().hex[:12]
    doc = {"texto": f"O protocolo {marca} escolhe um coordenador {marca} por maioria de votos",
           "origem": f"e2e-{marca}"}
    resposta = cliente.post(f"{BASE}/documentos", json=doc, timeout=TEMPO_LIMITE)
    assert resposta.status_code == 202, resposta.text
    caminho = resposta.json()["acompanhar"]

    estado = esperar(lambda: terminada(cliente, caminho))
    assert estado["estado"] == "concluida", estado
    return {**doc, "marca": marca, "tarefa": estado}


def test_saude(anonimo):
    assert anonimo.get(f"{BASE}/saude", timeout=TEMPO_LIMITE).json()["status"] == "ok"


@pytest.mark.parametrize("metodo, rota", [
    ("post", "/predict"), ("post", "/documentos"), ("get", "/tarefas/x"),
    ("post", "/buscar"), ("post", "/perguntar"),
])
def test_rotas_de_negocio_exigem_token(anonimo, metodo, rota):
    resposta = getattr(anonimo, metodo)(f"{BASE}{rota}", timeout=TEMPO_LIMITE)
    assert resposta.status_code == 401


def test_predicao_sincrona(cliente):
    resposta = cliente.post(f"{BASE}/predict", timeout=TEMPO_LIMITE,
                            json={"texto": "o atendimento foi excelente"})
    assert resposta.status_code == 200
    assert resposta.json()["sentimento"] == "positivo"


def test_documento_passa_pela_fila_e_aparece_na_busca(cliente, documento):
    resposta = cliente.post(f"{BASE}/buscar", timeout=TEMPO_LIMITE,
                            json={"pergunta": f"protocolo {documento['marca']}", "top_k": 5})
    assert resposta.status_code == 200
    assert resposta.json()["resultados"][0]["origem"] == documento["origem"]


def test_pergunta_recebe_resposta_fundamentada(cliente, documento):
    resposta = cliente.post(f"{BASE}/perguntar", timeout=TEMPO_LIMITE,
                            json={"pergunta": f"como o protocolo {documento['marca']} escolhe?"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert documento["origem"] in corpo["fontes"]
    assert documento["marca"] in corpo["resposta"]


def test_reenviar_o_mesmo_documento_nao_duplica(cliente, documento):
    resposta = cliente.post(f"{BASE}/documentos", timeout=TEMPO_LIMITE,
                            json={"texto": documento["texto"], "origem": documento["origem"]})
    caminho = resposta.json()["acompanhar"]
    estado = esperar(lambda: terminada(cliente, caminho))
    assert estado["novo"] == "0"
    assert estado["documento_id"] == documento["tarefa"]["documento_id"]


def test_tarefa_inexistente(cliente):
    resposta = cliente.get(f"{BASE}/tarefas/nao-existe", timeout=TEMPO_LIMITE)
    assert resposta.status_code == 404


def compose(*argumentos) -> str:
    return subprocess.run(["docker", "compose", *argumentos], cwd=RAIZ, check=True,
                          capture_output=True, text=True, timeout=120).stdout


def mortas() -> int:
    return int(compose("exec", "-T", "redis", "redis-cli", "llen", "fila:tarefas:dlq"))


JAEGER = os.getenv("URL_JAEGER", "http://localhost:16686")


def spans_da_tarefa(tarefa_id: str) -> list:
    """Spans (API v3 do Jaeger, formato OTLP) dos traces que citam a tarefa."""
    agora = datetime.now(UTC)
    resposta = requests.get(f"{JAEGER}/api/v3/traces", timeout=10, params={
        "query.service_name": "gateway",
        "query.attributes": json.dumps({"tarefa.id": tarefa_id}),
        "query.start_time_min": (agora - timedelta(hours=1)).isoformat(),
        "query.start_time_max": (agora + timedelta(minutes=1)).isoformat()})
    if resposta.status_code == 404:  # nada encontrado ainda
        return []
    resposta.raise_for_status()
    spans = []
    for recurso in resposta.json()["result"].get("resourceSpans", []):
        atributos = {a["key"]: a["value"] for a in recurso["resource"]["attributes"]}
        servico = atributos["service.name"]["stringValue"]
        for escopo in recurso["scopeSpans"]:
            spans += [{**span, "servico": servico} for span in escopo["spans"]]
    return spans


@pytest.mark.skipif(not LOCAL, reason="consulta o Jaeger do compose")
def test_um_trace_unico_vai_do_gateway_ao_banco(cliente):
    marca = uuid.uuid4().hex[:12]
    envio = cliente.post(f"{BASE}/documentos", timeout=TEMPO_LIMITE,
                         json={"texto": f"documento rastreado {marca}", "origem": marca}).json()
    assert esperar(lambda: terminada(cliente, envio["acompanhar"]))["estado"] == "concluida"

    def completo():
        spans = spans_da_tarefa(envio["id"])
        no_banco = any(s["servico"] == "worker" and s["name"] == "INSERT" for s in spans)
        servicos = {s["servico"] for s in spans}
        return spans if no_banco and {"gateway", "worker", "inferencia"} <= servicos else None

    spans = esperar(completo, segundos=40)
    assert len({s["traceId"] for s in spans}) == 1
    nomes = {s["name"] for s in spans}
    assert {"POST /documentos", "publicar fila:tarefas", "processar fila:tarefas",
            "POST /processar", "INSERT"} <= nomes
    exportado = json.dumps(spans)
    for proibido in (f"documento rastreado {marca}", "net.peer.ip", "client.address",
                     "user_agent"):
        assert proibido not in exportado


@pytest.mark.skipif(not LOCAL, reason="derruba containers: so no compose local")
def test_inferencia_fora_do_ar_degrada_e_depois_se_recupera(anonimo, cliente):
    def predizer():
        return cliente.post(f"{BASE}/predict", json={"texto": "muito bom"}, timeout=TEMPO_LIMITE)

    marca = uuid.uuid4().hex[:12]
    descartadas = mortas()
    compose("stop", "inferencia")
    try:
        for _ in range(4):
            resposta = predizer()
            assert resposta.status_code == 503
            assert "Retry-After" in resposta.headers
        saude = anonimo.get(f"{BASE}/saude", timeout=5).json()
        assert saude["disjuntores"]["inferencia"] == "aberto"

        envio = cliente.post(f"{BASE}/documentos", timeout=TEMPO_LIMITE,
                             json={"texto": f"documento enviado durante a falha {marca}",
                                   "origem": f"e2e-{marca}"})
        assert envio.status_code == 202  # a fila aceita mesmo com a inferencia fora
        caminho = envio.json()["acompanhar"]
        time.sleep(15)  # o worker tenta, falha, abre o proprio disjuntor e espera
        estado = cliente.get(f"{BASE}{caminho}", timeout=TEMPO_LIMITE).json()
        assert estado["estado"] == "pendente" and estado["tentativas"] == "0", estado
        assert mortas() == descartadas
    finally:
        compose("start", "inferencia")

    esperar(lambda: predizer().status_code == 200, segundos=90)
    estado = esperar(lambda: terminada(cliente, caminho), segundos=120)
    assert estado["estado"] == "concluida", estado
    saude = anonimo.get(f"{BASE}/saude", timeout=5).json()
    assert saude["disjuntores"]["inferencia"] == "fechado"
