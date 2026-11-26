"""Cliente do servico de inferencia: a IA existe num lugar so, o worker apenas pede."""
import os

import requests

from comum.web import cabecalhos_internos

URL_INFERENCIA = os.getenv("URL_INFERENCIA", "http://inferencia:8001")
TIMEOUT = float(os.getenv("TIMEOUT_INFERENCIA", "10"))
TIMEOUT_CONEXAO = float(os.getenv("TIMEOUT_CONEXAO", "5"))


def processar(texto: str) -> dict:
    """Devolve {sentimento, confianca, vetor}; levanta requests.RequestException."""
    resposta = requests.post(f"{URL_INFERENCIA}/processar", json={"texto": texto},
                             headers=cabecalhos_internos(),
                             timeout=(TIMEOUT_CONEXAO, TIMEOUT))
    resposta.raise_for_status()
    return resposta.json()
