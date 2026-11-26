# Servico de inferencia (modelo, embeddings, LLM).
# Build a partir da raiz: docker build -f inferencia/Dockerfile .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 PATH=/opt/venv/bin:$PATH

WORKDIR /app
# dependencias primeiro: a camada so e refeita quando o lock muda
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --only-group inferencia --no-cache

COPY comum comum
COPY vetorial vetorial
COPY inferencia inferencia
# treina o modelo no build: o usuario sem privilegios nao grava e o cold start fica menor
RUN python -m inferencia.modelo

RUN useradd --create-home app
USER app

EXPOSE 8001
# --no-access-log: o log de acesso do uvicorn grava o IP do cliente (LGPD)
CMD ["sh", "-c", "exec uvicorn inferencia.app:app --host 0.0.0.0 --port ${PORT:-8001} --no-access-log"]
