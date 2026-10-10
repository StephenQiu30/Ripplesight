FROM ghcr.io/astral-sh/uv:0.11.32 AS uv

FROM python:3.12-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=uv /uv /uvx /bin/

WORKDIR /srv/backend
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY sql ./sql
COPY app ./app

RUN useradd --create-home --uid 10001 ripplesight \
    && chown -R ripplesight:ripplesight /srv/backend

USER ripplesight
WORKDIR /srv/backend/app
EXPOSE 8080

CMD ["/srv/backend/.venv/bin/uvicorn", "main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-proxy-headers", "--no-access-log"]
