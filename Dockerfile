# syntax=docker/dockerfile:1

# Frontend (Next.js, exportação estática): o Node só existe neste estágio
FROM node:24-slim AS frontend
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm typecheck && pnpm build


FROM node:24-slim AS codex
RUN npm install --prefix /opt/codex --no-audit --no-fund @openai/codex@0.165.0 \
    && cp /opt/codex/node_modules/@openai/codex-linux-*/vendor/*/bin/codex /codex \
    && /codex --version


FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependências primeiro, para aproveitar o cache de camadas
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable


FROM python:3.12-slim-bookworm

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=frontend --chown=app:app /frontend/out /app/frontend
COPY --from=codex /codex /usr/local/bin/codex

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER 10001
EXPOSE 8000

ENTRYPOINT ["job-radar"]
CMD ["api"]
