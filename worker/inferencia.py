"""
Cliente do servico de inferencia: a IA existe num lugar so, o worker apenas pede.

disjuntor -> retentativa -> chamada com tempo-limite (Aula 11). /processar nao grava nada,
entao repetir e seguro.
"""
import os

import requests

from comum.circuit_breaker import CircuitBreaker
from comum.resiliencia import com_retentativa
from comum.web import cabecalhos_internos

URL_INFERENCIA = os.getenv("URL_INFERENCIA", "http://inferencia:8001")
TIMEOUT = float(os.getenv("TIMEOUT_INFERENCIA", "10"))
TIMEOUT_CONEXAO = float(os.getenv("TIMEOUT_CONEXAO", "5"))
PRAZO_TOTAL = float(os.getenv("PRAZO_INFERENCIA") or TIMEOUT * 1.5)
RETENTATIVAS = int(os.getenv("RETENTATIVAS", "3"))
BACKOFF_BASE = float(os.getenv("BACKOFF_BASE", "0.5"))

disjuntor = CircuitBreaker(limite_falhas=int(os.getenv("LIMITE_FALHAS", "3")),
                           espera_segundos=float(os.getenv("ESPERA_DISJUNTOR", "20")))


def chamar(texto: str, tempo_limite: float) -> requests.Response:
    """Uma tentativa; so 5xx e 429 sao levantados aqui (contam no disjuntor)."""
    resposta = requests.post(f"{URL_INFERENCIA}/processar", json={"texto": texto},
                             headers=cabecalhos_internos(),
                             timeout=(min(TIMEOUT_CONEXAO, tempo_limite), tempo_limite))
    if resposta.status_code == 429 or resposta.status_code >= 500:
        resposta.raise_for_status()
    return resposta


def processar(texto: str) -> dict:
    """
    Devolve {sentimento, confianca, vetor}. Levanta requests.RequestException ou
    CircuitoAberto.
    """
    tentar = com_retentativa(chamar, tentativas=RETENTATIVAS, base=BACKOFF_BASE,
                             prazo_total=PRAZO_TOTAL, tempo_limite=TIMEOUT)
    resposta = disjuntor.chamar(tentar, texto)
    resposta.raise_for_status()  # 4xx e erro nos dados: fora do disjuntor
    return resposta.json()
