# gateway/ — API Gateway (porta 8000)

Única entrada pública (Aula 8). Autentica, limita, roteia, registra. Sem modelo de IA e sem
acesso ao banco vetorial. Rotas: tabela no `CLAUDE.md` da raiz.

Estado: `app.py`, `Dockerfile` e `requirements.txt` são os do kit. Estenda o `app.py`
(pode dividir em módulos); troque o `Dockerfile` pelo padrão com `uv`. O `requirements.txt`
está desatualizado (versões com vulnerabilidades): as dependências valem pelo `uv.lock`.

## Autenticação (Tarefa 1, Aula 16)

- `POST /login` confere `USUARIO_DEMO`/`SENHA_DEMO` com `hmac.compare_digest` e emite JWT
  HS256 com `sub` e `exp` (`JWT_EXPIRA_MIN`). `HTTPBearer` do FastAPI dá o botão Authorize
  no `/docs`.
- 401 para token ausente, inválido ou expirado. Fixe `algorithms=["HS256"]` na verificação.
- As credenciais do ambiente publicado não vão para o repositório (ver `CLAUDE.md` da raiz).
- Segredo de `JWT_SEGREDO` (mínimo 32 bytes). O padrão serve só ao compose local; no Render o
  valor é gerado.

## Rate limit (Tarefa 2)

- Janela fixa no Redis (`INCR` + `EXPIRE` atômicos), `LIMITE_POR_MINUTO`; 429 com
  `Retry-After`.
- Cliente = `sub` do token; em `/login`, o IP **em hash** (dado pessoal: TTL de 60 s).
- Atrás do proxy do Render o IP vem em `X-Forwarded-For`; confirme na documentação qual
  posição é confiável, pois o cliente pode forjar o cabeçalho.
- Redis indisponível: deixe passar e registre o aviso (prioriza disponibilidade; citar nos
  trade-offs). `/saude` fica de fora.

## Roteamento e resiliência (Tarefa 6)

- Chamadas à inferência: `X-Token-Interno`, tempo-limite (`TIMEOUT_INFERENCIA`), retentativa
  e disjuntor. As rotas de leitura são idempotentes.
- Falha ou circuito aberto → 503 com `Retry-After` e mensagem genérica. `/perguntar` repassa o
  503 degradado da inferência (com trechos e fontes) sem trocar o corpo.
- Valide a entrada com os mesmos limites da inferência (`texto` não vazio e com tamanho
  máximo; `1 <= top_k <= 20`).
- Fila fora do ar em `/documentos` ou `/tarefas` → 503. Defina timeouts no cliente Redis.
- O formato da mensagem e das chaves está em `worker/CLAUDE.md`. Gateway e worker precisam
  concordar: coloque esse contrato em `comum/` para nenhum importar o outro.

## Cold start no Render

Serviços gratuitos dormem após 15 min sem requisições e levam ~1 min para voltar. O gateway
dispara em segundo plano (sem bloquear a resposta) um `GET /saude`:

- na própria subida, em `URL_INFERENCIA` e `URL_WORKER`;
- em `URL_WORKER`, ao enfileirar e ao consultar tarefa pendente. Sem isso a fila acumula com
  o worker dormindo.

A **inferência também dorme**. Com `TIMEOUT_INFERENCIA=10`, as chamadas síncronas dariam 503
durante o despertar e ainda abririam o disjuntor, justamente na primeira requisição de quem
for avaliar. Na nuvem, use um valor que cubra o cold start (da ordem de 75 a 90 s, conforme o
medido) e confira o comportamento depois de 15+ min ociosos. Tempo-limite longo multiplicado
por 3 retentativas deixaria o cliente esperando vários minutos: limite o tempo total.

**Observado no deploy:** o `GET /saude` vindo do gateway não acordou serviço adormecido; só o
acesso externo acordou. Por isso `GET /` publicado serve a página de `pagina.py`.
