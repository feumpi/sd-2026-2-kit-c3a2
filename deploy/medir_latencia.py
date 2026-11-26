"""
Mede a latencia das rotas pelo gateway, para o relatorio de trade-offs.

  uv run python deploy/medir_latencia.py                  # varias amostras, sistema acordado
  uv run python deploy/medir_latencia.py --primeiro-uso   # uma passada, para o cold start

Usa URL_BASE e as mesmas credenciais dos testes ponta a ponta (E2E_CREDENCIAIS ou
E2E_USUARIO/E2E_SENHA; sem nada, os padroes do compose local). Nao exibe credenciais.
No --primeiro-uso, o tempo inclui as respostas 503 e as esperas ate o primeiro sucesso.
"""
import argparse
import os
import statistics
import time
import uuid
from pathlib import Path

import requests

BASE = os.getenv("URL_BASE", "http://localhost:8000").rstrip("/")
TEMPO_LIMITE = 150
PRAZO = 300
INTERVALO_CONSULTA = float(os.getenv("INTERVALO_CONSULTA", "0.25"))


def credenciais() -> dict:
    arquivo = os.getenv("E2E_CREDENCIAIS")
    if arquivo:
        linhas = Path(arquivo).expanduser().read_text(encoding="utf-8").splitlines()
        valores = dict(linha.split("=", 1) for linha in linhas if "=" in linha)
        return {"usuario": valores["USUARIO_DEMO"], "senha": valores["SENHA_DEMO"]}
    return {"usuario": os.getenv("E2E_USUARIO", "aluno"),
            "senha": os.getenv("E2E_SENHA", "senha-local-do-compose")}


def chamar(sessao, metodo: str, rota: str, **opcoes) -> tuple[requests.Response, float, int]:
    """Repete enquanto vier 429 ou 503. Devolve (resposta, segundos, quantos 503).

    A espera do limite de requisicoes (429) nao conta no tempo; a do 503 conta.
    """
    inicio = time.monotonic()
    indisponiveis = 0
    while True:
        tentativa = time.monotonic()
        resposta = sessao.request(metodo, f"{BASE}{rota}", timeout=TEMPO_LIMITE, **opcoes)
        espera = float(resposta.headers.get("Retry-After", "5"))
        if resposta.status_code == 429:
            time.sleep(espera)
            inicio += time.monotonic() - tentativa
        elif resposta.status_code in (502, 503) and time.monotonic() - inicio < PRAZO:
            indisponiveis += 1
            time.sleep(espera)
        else:
            resposta.raise_for_status()
            return resposta, time.monotonic() - inicio, indisponiveis


def indexar(sessao) -> tuple[float, float, int]:
    """Envia um documento unico; devolve (tempo ate o 202, ate concluir, quantos 503)."""
    marca = uuid.uuid4().hex
    inicio = time.monotonic()
    envio, aceite, indisponiveis = chamar(
        sessao, "POST", "/documentos",
        json={"texto": f"medicao de latencia do documento {marca}", "origem": "medicao"})
    caminho = envio.json()["acompanhar"]
    while time.monotonic() - inicio < PRAZO:
        estado = chamar(sessao, "GET", caminho)[0].json()["estado"]
        if estado == "concluida":
            return aceite, time.monotonic() - inicio, indisponiveis
        if estado == "falhou":
            raise RuntimeError("a tarefa falhou")
        time.sleep(INTERVALO_CONSULTA)
    raise RuntimeError("a tarefa nao terminou a tempo")


def entrar(sessao) -> tuple[float, int]:
    resposta, segundos, indisponiveis = chamar(sessao, "POST", "/login", json=credenciais())
    sessao.headers["Authorization"] = f"Bearer {resposta.json()['token']}"
    return segundos, indisponiveis


CONSULTAS = [
    ("/predict", {"texto": "o atendimento foi excelente"}),
    ("/buscar", {"pergunta": "medicao de latencia", "top_k": 3}),
    ("/perguntar", {"pergunta": "o que diz a medicao de latencia?"}),
]


def primeiro_uso() -> None:
    sessao = requests.Session()
    total = time.monotonic()
    _, segundos, falhas = chamar(sessao, "GET", "/saude")
    linhas = [("GET /saude", segundos, falhas)]
    linhas.append(("POST /login", *entrar(sessao)))
    _, segundos, falhas = chamar(sessao, "POST", "/predict", json=CONSULTAS[0][1])
    linhas.append(("POST /predict", segundos, falhas))
    aceite, conclusao, falhas = indexar(sessao)
    linhas += [("POST /documentos (202)", aceite, falhas), ("documento concluido", conclusao, 0)]
    for rota, corpo in CONSULTAS[1:]:
        _, segundos, falhas = chamar(sessao, "POST", rota, json=corpo)
        linhas.append((f"POST {rota}", segundos, falhas))
    print("| etapa | segundos | respostas 503 antes do sucesso |\n|---|---|---|")
    for nome, segundos, falhas in linhas:
        print(f"| {nome} | {segundos:.2f} | {falhas} |")
    print(f"total: {time.monotonic() - total:.1f} s")


def amostras(quantas: int) -> None:
    sessao = requests.Session()
    entrar(sessao)
    tempos: dict[str, list[float]] = {}
    for _ in range(quantas):
        tempos.setdefault("GET /saude", []).append(chamar(sessao, "GET", "/saude")[1])
        aceite, conclusao, _ = indexar(sessao)
        tempos.setdefault("POST /documentos (202)", []).append(aceite)
        tempos.setdefault("documento concluido", []).append(conclusao)
        for rota, corpo in CONSULTAS:
            tempos.setdefault(f"POST {rota}", []).append(
                chamar(sessao, "POST", rota, json=corpo)[1])
    print(f"{quantas} amostras por rota\n| etapa | mediana (ms) | maximo (ms) |\n|---|---|---|")
    for nome, valores in tempos.items():
        print(f"| {nome} | {statistics.median(valores) * 1000:.0f} | {max(valores) * 1000:.0f} |")


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="Mede a latencia das rotas pelo gateway.")
    argumentos.add_argument("--primeiro-uso", action="store_true")
    argumentos.add_argument("--amostras", type=int, default=20)
    opcoes = argumentos.parse_args()
    primeiro_uso() if opcoes.primeiro_uso else amostras(opcoes.amostras)
