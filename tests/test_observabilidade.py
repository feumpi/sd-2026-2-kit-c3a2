"""TAREFA 7: um trace unico pela fila, trace_id nos logs e nada pessoal nos spans."""
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
import json
import logging
import threading

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.trace import SpanKind, Status, StatusCode

from comum import contrato, observabilidade
from gateway import app as gateway
from gateway import autenticacao
from worker import inferencia, worker

ANALISE = {"sentimento": "positivo", "confianca": 0.9, "vetor": [1.0] + [0.0] * 511}


class Repositorio:
    def gravar(self, *args):
        return "id", True


@pytest.fixture
def r(monkeypatch):
    falso = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(gateway, "redis_cliente", falso)
    return falso


def enviar(texto="texto sigiloso", **opcoes):
    token = autenticacao.emitir_token("usuario-teste")
    cliente = TestClient(gateway.app, client=("203.0.113.77", 4000), headers={
        "Authorization": f"Bearer {token}", "User-Agent": "navegador-da-maria"})
    resposta = cliente.post("/documentos", json={"texto": texto, "origem": "o"}, **opcoes)
    assert resposta.status_code == 202
    return resposta.json()["id"]


def por_tipo(spans, tipo):
    (span,) = [s for s in spans.get_finished_spans() if s.kind == tipo]
    return span


def test_um_unico_trace_atravessa_a_fila(r, spans, monkeypatch):
    monkeypatch.setattr(inferencia, "processar", lambda texto: ANALISE)
    tarefa_id = enviar()
    mensagem = json.loads(r.lindex(contrato.FILA, 0))
    assert "traceparent" in mensagem["contexto_trace"]

    worker.processar_uma(r, Repositorio(), parar=threading.Event(), espera=1)

    entrada = por_tipo(spans, SpanKind.SERVER)
    produtor = por_tipo(spans, SpanKind.PRODUCER)
    consumidor = por_tipo(spans, SpanKind.CONSUMER)
    assert {s.context.trace_id for s in (entrada, produtor, consumidor)} == {
        entrada.context.trace_id}
    assert produtor.parent.span_id == entrada.context.span_id
    assert consumidor.parent.span_id == produtor.context.span_id
    assert "fila:tarefas" in produtor.name and "fila:tarefas" in consumidor.name
    assert consumidor.attributes["tarefa.id"] == tarefa_id


def test_mensagem_sem_contexto_ainda_e_processada(r, spans, monkeypatch):
    monkeypatch.setattr(inferencia, "processar", lambda texto: ANALISE)
    contrato.enfileirar(r, {"texto": "t", "origem": "o"})
    worker.processar_uma(r, Repositorio(), parar=threading.Event(), espera=1)
    assert por_tipo(spans, SpanKind.CONSUMER).parent is None


def test_fila_vazia_nao_gera_span(r, spans):
    worker.processar_uma(r, Repositorio(), parar=threading.Event(), espera=1)
    assert spans.get_finished_spans() == ()


def test_spans_nao_levam_ip_agente_caminho_nem_texto(r, spans):
    enviar(params={"consulta": "segredo-na-url"})
    exportado = " ".join(s.to_json() for s in spans.get_finished_spans())
    for proibido in ("203.0.113.77", "navegador-da-maria", "segredo-na-url", "sigiloso",
                     "net.peer.ip", "client.address", "usuario-teste"):
        assert proibido not in exportado
    assert por_tipo(spans, SpanKind.SERVER).attributes["http.route"] == "/documentos"


def test_excecao_registrada_sem_mensagem_nem_pilha(spans):
    with pytest.raises(ValueError):
        with observabilidade.rastreador.start_as_current_span("quebra") as span:
            span.set_status(Status(StatusCode.ERROR, "dado pessoal na descricao"))
            raise ValueError("dado pessoal na mensagem")
    (span,) = spans.get_finished_spans()
    assert "dado pessoal" not in span.to_json()
    assert dict(span.events[0].attributes) == {"exception.type": "ValueError"}
    assert span.status.status_code == StatusCode.ERROR


def test_consulta_vazia_do_pool_nao_e_exportada(spans):
    for consulta in ("", "SELECT 1"):
        with observabilidade.rastreador.start_as_current_span(
                "banco", attributes={"db.system": "postgresql", "db.statement": consulta}):
            pass
    assert [s.attributes["db.statement"] for s in spans.get_finished_spans()] == ["SELECT 1"]


def test_saude_nao_e_rastreada(r, spans):
    TestClient(gateway.app).get("/saude")
    assert spans.get_finished_spans() == ()


def test_log_da_requisicao_leva_o_trace_id_do_span(r, spans, caplog):
    caplog.set_level(logging.INFO)
    enviar()
    entrada = por_tipo(spans, SpanKind.SERVER)
    (registro,) = [x for x in caplog.records if x.name == "requisicoes"]
    assert registro.trace_id == format(entrada.context.trace_id, "032x")


def test_log_do_worker_leva_o_mesmo_trace_id(r, spans, monkeypatch, caplog):
    monkeypatch.setattr(inferencia, "processar", lambda texto: ANALISE)
    enviar()
    caplog.set_level(logging.INFO)
    worker.processar_uma(r, Repositorio(), parar=threading.Event(), espera=1)
    (registro,) = [x for x in caplog.records if "concluida" in x.getMessage()]
    assert registro.trace_id == format(
        por_tipo(spans, SpanKind.PRODUCER).context.trace_id, "032x")


@pytest.mark.parametrize("endpoint, exporta", [("", False), ("http://coletor:4318", True)])
def test_so_exporta_quando_ha_endpoint(monkeypatch, endpoint, exporta):
    instalados = []
    monkeypatch.setattr(observabilidade.trace, "get_tracer_provider", lambda: None)
    monkeypatch.setattr(observabilidade.trace, "set_tracer_provider", instalados.append)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)
    monkeypatch.setenv("OTEL_SERVICE_NAME", "")
    observabilidade.iniciar_rastreamento("gateway")
    (provedor,) = instalados
    processadores = provedor._active_span_processor._span_processors
    assert bool(processadores) is exporta
    assert provedor.resource.attributes["service.name"] == "gateway"
    provedor.shutdown()


def test_instrumentar_um_app_novo_nao_duplica(spans):
    app = FastAPI()
    observabilidade.configurar(app, "teste")
    observabilidade.configurar(app, "teste")
