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
- Portas no host: só 8000 e 16686. Endereços por nome de serviço.
- Jaeger recebe OTLP/HTTP em `http://jaeger:4318`; interface em `localhost:16686`.

## Render + Neon + Honeycomb

Fatos conferidos na documentação do Render em 26/11/2026 (reconfira se algo divergir):

- Gratuito: 512 MB / 0,1 CPU; dorme após 15 min sem requisição de entrada; volta em ~1 min;
  750 h por workspace/mês; pode reiniciar a qualquer momento; sem disco persistente.
- **Não há background worker nem serviço privado gratuito.** Web service gratuito envia, mas
  **não recebe** tráfego de rede privada: serviços se chamam pelas URLs públicas HTTPS,
  protegidos pelo token interno.
- **Um** Key Value gratuito por workspace: 25 MB, 50 conexões, **sem persistência** (reinício
  perde a fila; registrar nos trade-offs).
- A aplicação escuta em `0.0.0.0:$PORT` (padrão 10000). TLS automático e redirecionamento de
  HTTP para HTTPS.
- Minutos de build são limitados no plano gratuito e, sem cartão cadastrado, estourar
  **desativa novos builds até o fim do mês**. São três imagens (a da inferência tem ~700 MB)
  a cada push: verifique na especificação do Blueprint os filtros de build por serviço (ou
  desligar o deploy automático) e, com o deploy no ar, agrupe os pushes.
- A documentação avisa que alto volume de tráfego iniciado pelo serviço pode suspendê-lo:
  não faça polling agressivo nem pings periódicos para manter serviços acordados.

`render.yaml` (Blueprint) na raiz: `type: web`, `runtime: docker`, `plan: free`,
`region: virginia` (mesma região do Neon), `dockerContext: .`,
`dockerfilePath: ./<servico>/Dockerfile`, `healthCheckPath: /saude`; `type: keyvalue`,
`plan: free`, `ipAllowList: []`, `maxmemoryPolicy: noeviction`. Segredos compartilhados em
`envVarGroups` com `generateValue: true` (`TOKEN_INTERNO`); o que vem de fora com
`sync: false`. `URL_INFERENCIA` e `URL_WORKER` precisam ser as URLs **públicas**
`https://….onrender.com`: `fromService` com `property: host`/`hostport` devolve endereço de
rede privada, que serviço gratuito não recebe. Confirme na especificação atual como
referenciar o Key Value e as URLs, e valide o arquivo antes (`render blueprints validate`, se o CLI existir).

## Passos que dependem do usuário

1. Criar contas Render e Honeycomb; criar o projeto Neon (ou autorizar você a criá-lo com
   `neonctl`, Postgres 17, `aws-us-east-1`, sem tocar nos projetos existentes).
2. No Render: New → Blueprint → este repositório → preencher as variáveis `sync: false`
   (`DATABASE_URL`, `OTEL_EXPORTER_OTLP_HEADERS`, `SENHA_DEMO`, …).
   O usuário digita os segredos no painel; não peça que os cole no chat.
3. O código precisa estar no GitHub (`main`); o Render publica a cada push.

Honeycomb: `OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io`,
`OTEL_EXPORTER_OTLP_HEADERS=x-honeycomb-team=<chave>`.

## Aceite do deploy

Com a URL pública: `/saude` 200; rota protegida sem token 401; login; `/predict`;
`/documentos` → tarefa `concluida`; `/buscar`; `/perguntar`; `http://` redireciona; repetir
depois de 15+ min ociosos; trace completo no Honeycomb; logs do painel sem dado pessoal;
inferência e worker recusam chamada sem token interno.
