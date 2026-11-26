# comum/ — código compartilhado entre serviços

Só o que é infraestrutura transversal. Nada de regra de negócio nem rotas.

| Arquivo | Origem | O que falta |
|---------|--------|-------------|
| `circuit_breaker.py` | C2, sem alteração | usar como está; ver cuidados abaixo |
| `resiliencia.py` | C2 (`geracao/`), sem alteração | ampliar a classificação de falhas se preciso |
| `observabilidade.py` | criar | tracer, instrumentação, propagação, logs |

Usado por todos os grupos de dependência: não importe aqui `sklearn`, `jwt` ou `psycopg`,
que não existem em todas as imagens.

## Resiliência (Aula 11)

- Composição: `disjuntor.chamar(com_retentativa(chamada_com_timeout))`. Uma sequência de
  tentativas esgotada conta como **uma** falha.
- **Cuidado:** `CircuitBreaker` conta qualquer `Exception` como falha. Um 4xx causado pela
  entrada do cliente não pode abrir o circuito: trate-o fora de `chamar` (devolva a resposta
  em vez de levantar) e valide a entrada já no gateway.
- Um disjuntor por dependência, por processo.
- `eh_transitoria` conhece só exceções do `requests`; erros transitórios do Postgres
  (`psycopg.OperationalError`) precisam ser tratados onde o banco é usado.

## Observabilidade (Aula 15)

- `OTEL_SERVICE_NAME` distinto por serviço (`gateway`, `inferencia`, `worker`).
- Exporter OTLP/HTTP padrão do OpenTelemetry, configurado só por ambiente:
  `OTEL_EXPORTER_OTLP_ENDPOINT` e `OTEL_EXPORTER_OTLP_HEADERS`. Sem endpoint, não exportar
  (testes e execução sem coletor não podem falhar nem poluir o log).
- Instrumentar FastAPI, `requests` e `psycopg`. Excluir `/saude` dos traces.
- **A fila não propaga contexto sozinha.** Ao enfileirar: `propagate.inject(carrier)` e
  gravar o `carrier` dentro da mensagem. Ao consumir: `propagate.extract(carrier)` e abrir o
  span com esse contexto (`SpanKind.PRODUCER` / `CONSUMER`). Sem isso o requisito R5 falha em
  silêncio: aparecem traces separados.
- Não instrumente o laço ocioso do worker no Redis (gera um trace a cada espera).
- Incluir `trace_id` nas linhas de log, para correlação.
- **LGPD:** a instrumentação FastAPI grava o IP do cliente nos spans. Confirmado nas versões
  travadas: `net.peer.ip` e `net.peer.port` (atrás de proxy podem surgir outros, como
  `http.client_ip` ou `client.address`). Remova-os antes de exportar e confira no Jaeger que
  não há IP, texto nem token. Vale para eventos de exceção.
- `instrument_app(app, excluded_urls="saude", exclude_spans=["receive", "send"])` evita os
  spans ASGI repetidos em cada requisição.
