"""Testes da retentativa com espera progressiva (Aula 11)."""
import pytest
import requests

from comum import resiliencia
from comum.resiliencia import com_retentativa, eh_transitoria


class Relogio:
    """Relogio falso: dormir so avanca o tempo."""

    def __init__(self):
        self.agora = 0.0
        self.esperas = []

    def monotonic(self):
        return self.agora

    def sleep(self, segundos):
        self.esperas.append(segundos)
        self.agora += segundos


@pytest.fixture
def relogio(monkeypatch):
    r = Relogio()
    monkeypatch.setattr(resiliencia.time, "monotonic", r.monotonic)
    monkeypatch.setattr(resiliencia.time, "sleep", r.sleep)
    monkeypatch.setattr(resiliencia.random, "uniform", lambda a, b: 0)
    return r


def erro_http(codigo):
    resposta = requests.Response()
    resposta.status_code = codigo
    return requests.HTTPError(response=resposta)


def sequencia(*itens):
    fila = list(itens)
    chamadas = []

    def funcao():
        chamadas.append(1)
        item = fila.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return funcao, chamadas


@pytest.mark.parametrize("erro, esperado", [
    (requests.Timeout(), True),
    (requests.ConnectionError(), True),
    (erro_http(500), True),
    (erro_http(503), True),
    (erro_http(429), True),
    (erro_http(422), False),
    (erro_http(401), False),
    (ValueError(), False),
])
def test_classificacao_de_falhas(erro, esperado):
    assert eh_transitoria(erro) is esperado


def test_backoff_dobra_a_cada_tentativa(relogio):
    funcao, chamadas = sequencia(requests.Timeout(), requests.Timeout(), "ok")
    assert com_retentativa(funcao, tentativas=3, base=0.5)() == "ok"
    assert len(chamadas) == 3
    assert relogio.esperas == [0.5, 1.0]


def test_erro_do_cliente_nao_e_retentado(relogio):
    funcao, chamadas = sequencia(erro_http(422), "ok")
    with pytest.raises(requests.HTTPError):
        com_retentativa(funcao)()
    assert len(chamadas) == 1


def test_desiste_apos_o_numero_de_tentativas(relogio):
    funcao, chamadas = sequencia(*[requests.Timeout()] * 5)
    with pytest.raises(requests.Timeout):
        com_retentativa(funcao, tentativas=3)()
    assert len(chamadas) == 3


def test_prazo_total_limita_a_sequencia(relogio):
    funcao, chamadas = sequencia(*[requests.Timeout()] * 10)
    with pytest.raises(requests.Timeout):
        com_retentativa(funcao, tentativas=10, base=1, prazo_total=5)()
    # esperas 1 e 2 cabem no prazo; a proxima (4) passaria dele
    assert relogio.esperas == [1, 2]
    assert len(chamadas) == 3


def test_log_nao_repete_a_mensagem_do_erro(relogio, caplog):
    funcao, _ = sequencia(requests.ConnectionError("http://x/?texto=segredo"), "ok")
    com_retentativa(funcao)()
    assert "ConnectionError" in caplog.text
    assert "segredo" not in caplog.text


def test_tempo_limite_de_cada_tentativa_cabe_no_que_resta_do_prazo(relogio):
    limites = []

    def lenta(tempo_limite):
        limites.append(tempo_limite)
        relogio.agora += tempo_limite  # consome todo o tempo da tentativa
        raise requests.Timeout()

    with pytest.raises(requests.Timeout):
        com_retentativa(lenta, tentativas=5, base=1, prazo_total=15, tempo_limite=10)()
    # 10 s + 1 s de espera + o que resta (4 s)
    assert limites == [10, 4]
    assert relogio.agora == 15
