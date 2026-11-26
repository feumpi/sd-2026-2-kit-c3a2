# API Gateway: porta de entrada unica.
# Build a partir da raiz: docker build -f gateway/Dockerfile .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 PATH=/opt/venv/bin:$PATH

WORKDIR /app
# dependencias primeiro: a camada so e refeita quando o lock muda
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --only-group gateway --no-cache

COPY comum comum
COPY gateway gateway

RUN useradd --create-home app
USER app

EXPOSE 8000
# --no-access-log: o log de acesso do uvicorn grava o IP do cliente (LGPD)
CMD ["sh", "-c", "exec uvicorn gateway.app:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
