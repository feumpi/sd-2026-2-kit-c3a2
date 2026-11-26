"""O medidor de latencia espera o 503 e o 429 sem contar a espera do limite."""
from types import SimpleNamespace

import pytest
import requests

from deploy import medir_latencia


class Relogio:

    def __init__(self):
        self.agora = 0.0

    def monotonic(self):
        return self.agora

    def sleep(self, segundos):
        self.agora += segundos


def resposta(status, espera="5"):
    r = requests.Response()
    r.status_code = status
    r.headers["Retry-After"] = espera
    return r


@pytest.mark.parametrize("status, segundos, indisponiveis", [(503, 6.0, 1), (429, 1.0, 0)])
def test_espera_do_503_conta_no_tempo_e_a_do_429_nao(monkeypatch, status, segundos,
                                                     indisponiveis):
    relogio = Relogio()
    monkeypatch.setattr(medir_latencia, "time", relogio)
    respostas = iter([resposta(status), resposta(200)])

    def pedir(*_, **__):
        relogio.agora += 0.5  # cada requisicao leva meio segundo
        return next(respostas)

    _, medido, falhas = medir_latencia.chamar(SimpleNamespace(request=pedir), "GET", "/x")

    assert (medido, falhas) == (segundos if status == 503 else 0.5, indisponiveis)
