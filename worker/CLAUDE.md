# worker/ — consumidor da fila (porta 8002)

Retira tarefas da fila, pede o processamento à inferência e grava no banco vetorial
(Aula 8). **Único escritor** do banco.

| Arquivo | Origem | O que fazer |
|---------|--------|-------------|
| `fila.py` | C2 `ingestao/`, sem alteração | renomear chaves para `fila:tarefas*`; levar o contrato compartilhado a `comum/` |
| `worker.py` | C2 `ingestao/`, sem alteração | trocar `indice.adicionar` pelo fluxo abaixo |
| `app.py` | criar | FastAPI com `/saude`; consumidor numa thread (lifespan) |

## Por que é um web service

O Render gratuito **não tem background worker**. O mesmo processo serve `/saude` (porta
`$PORT`) e consome a fila numa thread, localmente e na nuvem. O tratamento de `SIGTERM` do
C2 usa `signal.signal`, que só funciona na thread principal: troque por um
`threading.Event` acionado no encerramento do lifespan.

## Contrato

- `fila:tarefas`, `fila:tarefas:processando`, `fila:tarefas:dlq`, hash `tarefa:{id}`
  (TTL 24 h, **sem o texto**).
- Mensagem: `{id, documento: {texto, origem}, tentativas, criada_em, contexto_trace}`.
- Fila confiável: `BLMOVE` para `processando`, remover só depois de tratar, recuperar
  pendentes na subida. `recuperar_pendentes` pressupõe **um único worker**.

## Processamento

1. Extrair o contexto de rastreamento (ver `comum/CLAUDE.md`).
2. `POST {URL_INFERENCIA}/processar` com token interno, tempo-limite, retentativa e disjuntor.
3. Gravar no pgvector (idempotente) e marcar `concluida`.

## Falhas — atenção, o comportamento do C2 não serve aqui

O C2 reenfileira na hora e manda à dead-letter na 3ª tentativa. Com a inferência em cold
start (~1 min) ou o disjuntor aberto, isso descartaria tarefas boas em segundos.

- **Transitória** (timeout, conexão, 5xx, 429, circuito aberto, banco indisponível): esperar
  (backoff ou `segundos_para_tentar()`) e reenfileirar **sem gastar tentativa**; só vai à
  dead-letter ao passar de `TAREFA_IDADE_MAXIMA` segundos.
- **Permanente** (4xx, erro nos dados): até `MAX_TENTATIVAS`, depois dead-letter.
- Mensagem malformada: direto para a dead-letter.
- `TIMEOUT_INFERENCIA` maior na nuvem (~90 s) para atravessar o cold start.
- Redis fora do ar: esperar e reconectar, sem derrubar o processo. Se a thread morrer,
  `/saude` precisa acusar.

## Retenção (LGPD)

Rotina periódica (e na subida) que apaga documentos com mais de `RETENCAO_DIAS`. A
dead-letter contém texto: limite o prazo dela também (ex.: `EXPIRE` na lista). O README só
pode declarar prazos realmente aplicados.
