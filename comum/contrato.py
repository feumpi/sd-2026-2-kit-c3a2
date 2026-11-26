"""
Contrato da fila de tarefas no Redis (Aula 8), compartilhado por gateway e worker.

Produtor (gateway, POST /documentos) -> fila:tarefas -> consumidor (worker).

  fila:tarefas              mensagens aguardando processamento
  fila:tarefas:processando  mensagem que o worker pegou e ainda nao terminou
  fila:tarefas:dlq          dead-letter: mensagens descartadas, para analise
  tarefa:{id}               hash com o estado da tarefa, sem o texto do documento

Mensagem: {id, documento: {texto, origem}, tentativas, criada_em, contexto_trace}
"""
import json
import os
import time
import uuid

import redis

FILA = "fila:tarefas"
PROCESSANDO = "fila:tarefas:processando"
DLQ = "fila:tarefas:dlq"

PENDENTE = "pendente"
CONCLUIDA = "concluida"
FALHOU = "falhou"

# prazos de retencao (segundos): o texto so fica na fila ate ser processado
VALIDADE_TAREFA = int(os.getenv("TAREFA_VALIDADE", str(24 * 60 * 60)))


def conectar() -> redis.Redis:
    """Cliente com tempo-limite em toda operacao; a conexao so abre no primeiro uso."""
    return redis.Redis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True,
        socket_timeout=float(os.getenv("REDIS_TIMEOUT", "5")),
        socket_connect_timeout=float(os.getenv("REDIS_TIMEOUT_CONEXAO", "3")),
    )


def chave_tarefa(tarefa_id: str) -> str:
    return f"tarefa:{tarefa_id}"


def atualizar_tarefa(r, tarefa_id: str, **campos) -> None:
    """Grava campos do estado e renova o prazo de expiracao."""
    r.hset(chave_tarefa(tarefa_id), mapping={k: str(v) for k, v in campos.items()})
    r.expire(chave_tarefa(tarefa_id), VALIDADE_TAREFA)


def enfileirar(r: redis.Redis, documento: dict, contexto_trace: dict | None = None) -> str:
    """Publica o documento na fila e devolve o identificador da tarefa."""
    tarefa_id = uuid.uuid4().hex
    agora = time.time()
    mensagem = {"id": tarefa_id, "documento": documento, "tentativas": 0,
                "criada_em": agora, "contexto_trace": contexto_trace or {}}
    # transacao: ou o estado e a mensagem sao gravados, ou nada
    with r.pipeline(transaction=True) as lote:
        atualizar_tarefa(lote, tarefa_id, estado=PENDENTE, tentativas=0, criada_em=agora)
        lote.lpush(FILA, json.dumps(mensagem))
        lote.expire(FILA, VALIDADE_TAREFA)
        lote.execute()
    return tarefa_id


def consultar_tarefa(r: redis.Redis, tarefa_id: str) -> dict | None:
    dados = r.hgetall(chave_tarefa(tarefa_id))
    return dict(dados) or None  # type: ignore[arg-type]
