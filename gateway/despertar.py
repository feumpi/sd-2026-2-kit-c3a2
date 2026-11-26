"""
Acorda os servicos que dormem no plano gratuito (cold start).

Dispara um GET /saude em segundo plano, sem atrasar a resposta ao cliente, e no maximo uma
vez a cada INTERVALO por servico. Nao e um ping periodico para manter servicos acordados.

No ambiente publicado isto mantem ativo um servico ja acordado, mas nao acordou um
adormecido; quem acorda e o acesso externo (ver pagina.py).
"""
import os
import threading
import time

import requests
from opentelemetry.instrumentation.utils import suppress_instrumentation

ATIVO = os.getenv("DESPERTAR_SERVICOS", "1") == "1"
INTERVALO = float(os.getenv("DESPERTAR_INTERVALO", "30"))
TIMEOUT = float(os.getenv("DESPERTAR_TIMEOUT", "90"))

_ultimo: dict[str, float] = {}
_trava = threading.Lock()


def _chamar(url: str) -> None:
    try:
        with suppress_instrumentation():  # nao gera trace
            requests.get(f"{url}/saude", timeout=TIMEOUT)
    except requests.RequestException:
        pass  # e so um empurrao; quem precisar do servico trata a falha


def despertar(*urls: str) -> None:
    if not ATIVO:
        return
    agora = time.monotonic()
    for url in urls:
        with _trava:
            if agora - _ultimo.get(url, -INTERVALO) < INTERVALO:
                continue
            _ultimo[url] = agora
        threading.Thread(target=_chamar, args=(url,), daemon=True).start()
