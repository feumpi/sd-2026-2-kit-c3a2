# deploy/ — containers, compose e publicação

Vale para os Dockerfiles, o `docker-compose.yml`, o `.dockerignore` e o `render.yaml`.
`INSTRUCOES.md` é o texto do kit: ao publicar, reescreva-o com os passos reais.

## Padrão de Dockerfile (instalação testada em arm64 em 26/11/2026)

```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --only-group gateway --no-cache
COPY comum comum
COPY gateway gateway
RUN useradd --create-home app
USER app
CMD ["sh", "-c", "exec uvicorn gateway.app:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
```

- Contexto de build = raiz. Troque grupo, pastas e porta (8001 inferência, 8002 worker).
- Inferência e worker também copiam `vetorial/`; a inferência treina o modelo no build.
- `.dockerignore`: `.git`, `.venv`, `.env*`, `docs`, `referencia`, `tests`, `**/CLAUDE.md`,
  `**/__pycache__`, `*.joblib`. (`vetorial/esquema.sql` precisa continuar incluído.)

## Compose (modelo: `referencia/c2a2/docker-compose.yml`)

- Um comando: `docker compose up --build`, **sem exigir `.env`** (padrões com
  `${VAR:-padrao}`).
- Serviços: `redis`, `vetorial`, `inferencia`, `worker`, `gateway`, `jaeger`.
- Healthchecks e `depends_on: condition: service_healthy`; `restart: unless-stopped`. A
  imagem slim não tem curl: use `python -c` com `urllib`.
- Portas no host: só 8000 e 16686. Endereços por nome de serviço. Nunca `5432:5432`: o host
  já tem um Postgres nessa porta.
- Jaeger recebe OTLP/HTTP em `http://jaeger:4318`; interface em `localhost:16686`.

## Render + Honeycomb

Fatos conferidos na documentação do Render em 26/11/2026 (reconfira se algo divergir):

- Web gratuito: 512 MB / 0,1 CPU; dorme após 15 min sem requisição de entrada; volta em
  ~1 min; 750 h por workspace/mês; pode reiniciar a qualquer momento; sem disco persistente.
- **Não há background worker nem serviço privado gratuito.** Web service gratuito envia, mas
  **não recebe** tráfego de rede privada: serviços se chamam pelas URLs públicas HTTPS,
  protegidos pelo token interno. Já o Key Value e o Postgres são alcançados pela rede privada
  (mesma conta e região).
- **Um** Key Value gratuito por workspace: 25 MB, 50 conexões, **sem persistência**.
- **Um** Postgres gratuito por workspace: 1 GB, **expira 30 dias após a criação** (mais 14
  dias de carência antes de ser apagado), sem backup e sem pooler.
- A aplicação escuta em `0.0.0.0:$PORT` (padrão 10000). TLS automático e redirecionamento de
  HTTP para HTTPS.
- Minutos de build são limitados e, sem cartão cadastrado, estourar **desativa novos builds
  até o fim do mês**. O rascunho usa `buildFilter` por serviço e ignora `*.md`; ainda assim, agrupe os pushes
  depois que o deploy estiver no ar.
- Banda de saída também é limitada; sem cartão, estourar suspende os serviços gratuitos.
- A documentação avisa que alto volume de tráfego iniciado pelo serviço pode suspendê-lo:
  não faça polling agressivo nem pings periódicos para manter serviços acordados.

## Blueprint

[render.yaml](../render.yaml) passou no `render blueprints validate`, que confirma o esquema,
não o comportamento. Observado no primeiro deploy: com `URL_INFERENCIA`/`URL_WORKER` vindas de
`envVarKey: RENDER_EXTERNAL_URL` de outro serviço, a sincronização ficou presa; com as URLs
públicas fixas, prosseguiu. Não troque por `property: host`/`hostport`, que são endereços de
rede privada. O plugin do Render roda `render blueprints validate` a cada edição desse arquivo.

## Passos que dependem do usuário

1. GitHub conectado ao Render: **feito** (informado pelo usuário em 26/11; só se confirma de
   fato ao criar o Blueprint). Se o repositório não aparecer, peça para revisar o acesso do app.
2. Com o `render.yaml` já na `main`, criar o Blueprint: no painel, New → Blueprint → este repositório; ou, com confirmação do
   usuário, `render ea blueprints create` (recurso em acesso antecipado).
3. Só então, com os campos à vista no painel, pedir ao usuário que crie a **Ingest key** no
   Honeycomb (Environments → Manage Environments → API Keys → Ingest; aparece uma única vez) e
   preencha as variáveis `sync: false`:
   - `OTEL_EXPORTER_OTLP_HEADERS` = `x-honeycomb-team=<chave>` (o par chave=valor, não só a
     chave), nos três serviços.
   - `USUARIO_DEMO` e `SENHA_DEMO` (senha forte e exclusiva), no gateway.

   O usuário digita os segredos no painel; não peça que os cole no chat nem os grave no
   repositório.
4. O código precisa estar no GitHub (`main`); o Render publica a cada push.

Honeycomb (região US): `OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io`. Localmente não
é preciso chave: o compose usa o Jaeger.

## Aceite do deploy

Com a URL pública: `/saude` 200; rota protegida sem token 401; login; `/predict`;
`/documentos` → tarefa `concluida`; `/buscar`; `/perguntar`; `http://` redireciona; repetir
depois de 15+ min ociosos; trace completo no Honeycomb; logs do painel sem dado pessoal;
inferência e worker recusam chamada sem token interno. Informe ao usuário a data em que o
banco gratuito expira.
