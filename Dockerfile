# syntax=docker/dockerfile:1
#
# Build:  docker build -t gg-agent-server:dev .
# Run:    docker run --rm -p 8000:8000 gg-agent-server:dev
# Health: curl http://127.0.0.1:8000/health

ARG PYTHON_VERSION=3.12

FROM node:22.23.1-bookworm-slim AS pi-runtime

RUN npm install --global --ignore-scripts --no-audit --no-fund \
    @earendil-works/pi-coding-agent@0.83.0

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/gg-sdk ./packages/gg-sdk
COPY packages/gg-server ./packages/gg-server

ENV UV_PROJECT_ENVIRONMENT=/app/.venv
RUN uv sync --frozen --no-dev --no-editable --package gg-server

FROM python:${PYTHON_VERSION}-slim-bookworm

ARG USERNAME=gg
ARG UID=10001
ARG GID=10001

RUN groupadd -g ${GID} ${USERNAME} \
 && useradd -m -u ${UID} -g ${GID} -s /usr/sbin/nologin ${USERNAME} \
 && mkdir -p /workspace/project /workspace/conversations \
 && chown -R ${USERNAME}:${USERNAME} /workspace

COPY --from=builder /app/.venv /app/.venv
COPY --from=pi-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=pi-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && ln -s ../lib/node_modules/@earendil-works/pi-coding-agent/dist/cli.js \
    /usr/local/bin/pi \
 && test "$(node --version)" = "v22.23.1" \
 && test "$(pi --version)" = "0.83.0"

ENV PATH="/app/.venv/bin:$PATH" \
    GG_WORKSPACE_DIR=/workspace/project \
    GG_CONVERSATIONS_DIR=/workspace/conversations

USER ${USERNAME}
WORKDIR /workspace/project

EXPOSE 8000

CMD ["python", "-m", "gg.server", "--host", "0.0.0.0", "--port", "8000"]
