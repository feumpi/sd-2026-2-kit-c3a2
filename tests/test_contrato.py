"""Testes do contrato da fila compartilhado por gateway e worker."""
import json

import fakeredis
import pytest

from comum import contrato

DOC = {"texto": "texto sigiloso do documento", "origem": "teste"}


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


def test_enfileirar_publica_mensagem_e_estado_pendente(r):
    tarefa_id = contrato.enfileirar(r, DOC, {"traceparent": "00-abc"})
    mensagem = json.loads(r.lindex(contrato.FILA, 0))
    assert mensagem["id"] == tarefa_id
    assert mensagem["documento"] == DOC
    assert mensagem["tentativas"] == 0
    assert mensagem["contexto_trace"] == {"traceparent": "00-abc"}
    assert contrato.consultar_tarefa(r, tarefa_id)["estado"] == contrato.PENDENTE


def test_estado_da_tarefa_nao_guarda_o_texto_e_expira(r):
    tarefa_id = contrato.enfileirar(r, DOC)
    assert "sigiloso" not in json.dumps(contrato.consultar_tarefa(r, tarefa_id))
    assert 0 < r.ttl(contrato.chave_tarefa(tarefa_id)) <= contrato.VALIDADE_TAREFA
    assert 0 < r.ttl(contrato.FILA) <= contrato.VALIDADE_TAREFA


def test_tarefa_inexistente(r):
    assert contrato.consultar_tarefa(r, "nao-existe") is None


def test_cliente_tem_tempo_limite():
    opcoes = contrato.conectar().connection_pool.connection_kwargs
    assert opcoes["socket_timeout"] > 0
    assert opcoes["socket_connect_timeout"] > 0
