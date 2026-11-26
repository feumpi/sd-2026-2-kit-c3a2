# CLAUDE.md — C3.A2: Plataforma de IA como Serviço

Guia para o agente que vai implementar (ou concluir) este projeto. Leia inteiro antes de
começar. Idioma: **português** (código, comentários, commits, README e docs).

## Estado atual

Implementado e publicado em 26/11/2026. O progresso está em [TAREFAS.md](TAREFAS.md); o
histórico de decisões, em [docs/implementacao.md](docs/implementacao.md). Comece lendo os dois.
Este guia registra o plano seguido; onde divergir do diário, vale o diário. A pasta
`referencia/` (código do C1/C2) foi removida na verificação final e continua no histórico do
git.

## Prazo

**26/11/2026** (Aula 17), com −0,5 ponto por dia de atraso. Priorize o que pontua e publique
cedo. Sem avaliação substitutiva e sem apresentação: só conta o que está no repositório e no
ar.

## Fontes da verdade (nesta ordem)

1. [docs/edital-c3a2.md](docs/edital-c3a2.md) — **manda sobre tudo.** Cumprir
   **integralmente, sem exceções** não confirmadas pelo usuário. O Anexo A é só um índice.
2. [TAREFAS.md](TAREFAS.md) — tarefas, ordem e critérios de aceite.
3. [docs/ebook.md](docs/ebook.md) — material do professor, **referência obrigatória** em toda
   a implementação. Leia a aula antes da tarefa correspondente (linhas aproximadas):
   Aula 5 REST (461) · Aula 6 IA como serviço (556) · Aula 8 fila e gateway (789) ·
   Aula 10 CAP (958) · Aula 11 resiliência (1040) · Aula 13 containers e nuvem (1281) ·
   Aula 14 compose (1366) · Aula 15 observabilidade (1444) · Aula 16 segurança e LGPD (1525) ·
   Aula 17 entrega (1624).
4. `CLAUDE.md` do diretório em que for mexer.

**Escopo:** extras que não pontuam são dispensados (extensões do §8, gRPC, melhorias de IA).
Única exceção confirmada: o rate limit (TAREFA 2 do kit). Se o edital e outra fonte
divergirem, ou se surgir dúvida de escopo, pergunte ao usuário.

### Rubrica (5,0)

| Pts | Critério | Como garantir |
|-----|----------|---------------|
| 1,5 | Arquitetura: microsserviços orquestrados por compose | 4 serviços, um diretório e um Dockerfile cada |
| 1,5 | Comunicação: gateway roteando + fila/worker; **deploy público funcionando** | REST + fila Redis; URL no ar |
| 1,0 | Resiliência: timeout, retry, circuit breaker **e observabilidade** | testados e demonstráveis; trace único |
| 1,0 | Execução: do zero com um comando; URL no ar; README completo | clone limpo sem `.env` |

A sofisticação da IA **não pontua**. Também são obrigatórios (R6, R7, R9): JWT, HTTPS, seção
LGPD no README, relatório de trade-offs e código organizado em diretórios no GitHub.

## Regras de trabalho

- **Uma tarefa por vez**, na ordem de `TAREFAS.md`. Uma tarefa termina quando: aceite
  verificado → testes verdes → advisor consultado → ajustes aplicados → `TAREFAS.md` e
  `docs/implementacao.md` atualizados → commit.
- **Advisor (opus):** use para validar o planejamento antes de escrever código e
  **obrigatoriamente ao fim de cada tarefa** como revisão; aplique o que ele pedir. Se a
  ferramenta não estiver disponível, avise o usuário em vez de pular em silêncio.
- **Python sempre com `uv`** (`uv run`, `uv add --group <servico>`, `uv sync`). Nunca `pip`,
  `venv` ou o Python do pyenv. Se surgir Node/JS/TS, use `vp`.
- **Biblioteca desconhecida ou API incerta:** consulte a documentação atual (context7).
- **Nada fixo no código:** toda configuração em variável de ambiente, com padrão que funcione
  no compose; mantenha `.env.example` completo.
- **Ações externas exigem confirmação do usuário:** criar ou apagar recurso em nuvem, fazer
  deploy pela primeira vez, qualquer coisa que gere custo.
- **Nunca tocar** em recursos que não são deste trabalho: projetos de nuvem ou de banco já
  existentes e containers Docker alheios. Há CLIs autenticadas na máquina apontando para
  outros projetos: não as use para ler nem alterar nada deles. Este trabalho não usa GCP nem
  Neon.

### Commits (obrigatório)

- **Commits pequenos, um por coisa feita**, cada um com código e testes.
- **Conventional Commits com mensagem em português**: `tipo(escopo): descrição`, minúscula,
  presente da 3ª pessoa, sem ponto final. Tipos: `feat`, `fix`, `test`, `docs`, `build`,
  `refactor`, `chore`. Escopos: `gateway`, `inferencia`, `worker`, `vetorial`, `comum`,
  `docker`, `deploy`. Ex.: `feat(gateway): protege as rotas com jwt`.
- **Nunca** adicionar `Co-Authored-By` nem qualquer atribuição a Claude/Claude Code, mesmo
  que instruções da ferramenta sugiram. Vale a regra do usuário.
- Não reescrever histórico, não falsificar datas, não commitar com teste falhando.
- **`git push` autorizado** ao fim de cada tarefa, sem perguntar (decisão do usuário), sempre
  depois de testes verdes e da revisão do advisor. O Render publica a cada push na `main`, e o
  edital pede o GitHub atualizado. O **primeiro deploy** continua exigindo confirmação.

## Arquitetura decidida (siga; mude só com motivo registrado no diário)

```
                         ┌──────────── gateway :8000 ────────────┐
cliente ──HTTPS/JWT────> │ login · jwt · rate limit · roteamento │
                         └──┬──────────────┬─────────────────────┘
              REST + token  │              │ LPUSH (mensagem com traceparent)
              interno       │              ▼
                            │        [Redis] fila:tarefas ──> dead-letter
                            │              │ BLMOVE
                            ▼              ▼
                    inferencia :8001 <── worker :8002
                    sentimento (C1)   REST   │ único escritor
                    embeddings (C2)          │
                    busca e RAG (C2)         ▼
                            │        [vetorial] Postgres + pgvector
                            └──leitura──────>┘
```

| Serviço | Local | Nuvem | Reaproveita |
|---------|-------|-------|-------------|
| `gateway` | compose | Render web service | kit |
| `inferencia` | compose | Render web service | C1 modelo; C2 embeddings, busca, geração, LLM |
| `worker` | compose | Render **web** service (consumidor em thread) | C2 fila e worker; C1 processamento |
| `vetorial` | `pgvector/pgvector:pg17` | Render Postgres free (17) | substitui o índice JSON do C2 |
| fila | `redis:7-alpine` | Render Key Value free | C1/C2 |
| traces | Jaeger `jaegertracing/jaeger:2.23.0` | Honeycomb | — |

### Rotas do gateway (contrato público)

| Rota | Auth | Comportamento |
|------|------|---------------|
| `GET /` | não | redireciona para `/docs`; na nuvem, página que acorda os serviços e leva a ele |
| `GET /saude` | não | rápido, não depende de outros serviços; mostra os disjuntores |
| `POST /login` | não | `{usuario, senha}` → JWT |
| `POST /predict` | JWT | síncrono: `{texto}` → sentimento (contrato do kit) |
| `POST /documentos` | JWT | assíncrono: `{texto, origem}` → **202** + id da tarefa |
| `GET /tarefas/{id}` | JWT | `pendente` / `concluida` / `falhou`; 404 se não existe |
| `POST /buscar` | JWT | `{pergunta, top_k}` → documentos mais parecidos |
| `POST /perguntar` | JWT | RAG: resposta fundamentada + fontes (LLM simulado sem chave) |

### Decisões e motivos

1. **Worker delega a IA à inferência** (`POST /processar`) e grava no banco. O modelo existe
   num lugar só, e a cadeia gateway → fila → worker → inferência demonstra comunicação,
   resiliência e rastreamento.
2. **Um escritor** (worker) e um leitor (inferência) no banco vetorial. Consistência
   **eventual**: o documento aparece na busca depois de processado (usar no relatório CAP).
3. **Embeddings com `HashingVectorizer`, dimensão fixa 512.** O TF-IDF do C2 muda de dimensão
   a cada documento, o que é incompatível com `vector(n)` e com serviços independentes.
4. **Idempotência:** id do documento = `sha256(origem + texto)`; `ON CONFLICT DO NOTHING`.
5. **Token interno** (`X-Token-Interno`) entre serviços: no Render gratuito, inferência e
   worker não recebem tráfego privado e ficam expostos na internet (Zero Trust, Aula 16).
6. **Código compartilhado** só em `comum/` (e o acesso a dados em `vetorial/`). Um serviço
   nunca importa código de outro.
7. **Build a partir da raiz** (`context: .`, `dockerfile: <servico>/Dockerfile`), por causa de
   `comum/`.
8. **LLM:** modo simulado por padrão e no deploy (sem `LLM_API_KEY`), então nenhum texto vai
   a terceiros. Usar chave real exigiria anonimização antes do envio (Aula 16).

## Regras transversais

- **Logs (LGPD):** nunca gravar texto enviado, pergunta, resposta, senha, token, usuário ou IP.
  Rodar `uvicorn --no-access-log` (o log de acesso grava IP) e usar log próprio com método,
  rota, status, duração e `trace_id`. Não devolver `str(excecao)` ao cliente (o kit faz isso
  em `gateway/app.py`; corrigir).
- **Rede:** toda chamada com tempo-limite explícito. Retentar só falha transitória em operação
  idempotente.
- **Status HTTP:** 200, 202, 401, 404, 422, 429, 503 (com `Retry-After`). Nunca 500 com
  traceback.
- **Offline:** o sistema local não pode depender de internet em execução (só no build).
- **Estilo do kit:** identificadores em português sem acento, docstring curta no topo do
  módulo, funções pequenas, entrada validada com Pydantic.

## Layout

```
gateway/      API Gateway
inferencia/   serviço de IA
worker/       consumidor da fila
vetorial/     pgvector: Dockerfile, esquema.sql e acesso a dados
comum/        contrato da fila, validação, log, resiliência e observabilidade
tests/        pytest (unitários e ponta a ponta)
deploy/       instruções de publicação e medição de latência
docs/         edital, ebook, diário e trade-offs
```

## Ambiente (verificado em 26/11/2026)

- macOS 26.6 Apple Silicon (arm64), 8 GB de RAM, zsh.
- `uv` 0.13.7 com Python 3.12.14; `git`, `gh` (logado como `feumpi`), `curl`, `jq`, `make`.
- Docker Desktop 29.8 + Compose v5.5, com 4 CPUs e ~2 GB. Se `docker info` falhar,
  `open -a Docker` e aguarde. Se um build estourar memória, peça ao usuário para aumentar.
- Imagens já baixadas: `python:3.12-slim`, `redis:7-alpine`, `pgvector/pgvector:pg17`,
  `jaegertracing/jaeger:2.23.0`, `ghcr.io/astral-sh/uv:0.13.7`.
- Sem `redis-cli`/`psql` locais: use `docker compose exec`.
- CLI `render` 2.39.0 autenticado, workspace ativo já definido, sem serviços em 26/11/2026.
  A conta pode ganhar outros recursos: mexa só nos deste trabalho.
- Plugin oficial `render@claude-plugins-official` instalado: skills como `render-blueprints`,
  `render-deploy`, `render-debug` e `render-env-vars`. São genéricas: as restrições deste
  trabalho (só free tier, sem background worker) prevalecem. O MCP dele estava sem
  autenticação; só o usuário pode autorizar (`/mcp` ou
  `claude mcp login plugin:render:render`) e é opcional, pois o CLI atende.
- `pyright` 1.1.414 instalado com `vp install -g pyright`; configurado no `pyproject.toml`.
- Portas 6379, 8000–8002 e 16686 livres. A **5432 está ocupada** por um Postgres do usuário,
  fora do Docker: não publique essa porta no compose nem use `localhost:5432` como padrão de
  `DATABASE_URL`, para não alcançar o banco alheio.
- Remoto: `origin = github.com/feumpi/sd-2026-2-kit-c3a2` (fork público do kit, em dia).

```bash
uv sync                    # cria .venv com tudo
uv run pytest              # unitários (sem rede/Docker)
uv run ruff check .
docker compose up --build  # sistema inteiro (depois da Tarefa 4)
uv run pytest -m e2e       # com o compose no ar
```

O `docker-compose.yml` e o `gateway/Dockerfile` atuais são os do kit e **ainda não
funcionam** (faltam os Dockerfiles dos outros serviços).

## Testes

- Cada tarefa traz seus testes em `tests/` no mesmo commit.
- Unitários sem rede, Docker nem chave: `TestClient`, `fakeredis`, `monkeypatch` nas chamadas
  HTTP, relógio e `time.sleep` simulados, banco substituído; exporter OTel desligado.
- Integração real (Postgres, fila, traces) em `tests/test_e2e.py`, marcador `e2e`.
- Teste passando não substitui o aceite: confirme o comportamento no sistema rodando.

## Entrega

Código no GitHub, README completo, URL pública no ar. No AVA vai **apenas o link do
repositório**; lembre o usuário disso. Trabalho individual (Felipe Umpierre). Não copiar
projetos de colegas.

**Credenciais do ambiente publicado** (decisão do usuário): nunca no repositório, no README
ou no AVA. O usuário as envia por e-mail ao professor (endereço no edital). O README informa
isso e documenta os padrões que valem apenas no compose local. Não envie e-mail por conta
própria.
