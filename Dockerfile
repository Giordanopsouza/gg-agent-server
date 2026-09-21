# syntax=docker/dockerfile:1
#
# Build:  docker build -t gg-agent-server:dev .
# Run:    docker run --rm -p 8000:8000 gg-agent-server:dev
# Health: curl http://127.0.0.1:8000/health

ARG PYTHON_VERSION=3.12.11

FROM node:22.23.1-bookworm-slim AS pi-runtime

RUN npm install --global --ignore-scripts --no-audit --no-fund \
    @earendil-works/pi-coding-agent@0.83.0

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /uvx /bin/

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
ARG TARGETARCH

RUN groupadd -g ${GID} ${USERNAME} \
 && useradd -m -u ${UID} -g ${GID} -s /usr/sbin/nologin ${USERNAME} \
 && mkdir -p /workspace/project /workspace/conversations \
 && chown -R ${USERNAME}:${USERNAME} /workspace

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git=1:2.39.5-0+deb12u3 \
 && case "${TARGETARCH}" in \
      amd64) gh_sha256=e4d4bb4498e8d007abe545b6568926793ace1b6447da598294a610018cb164be ;; \
      arm64) gh_sha256=ea4e7a581a32ccad6cc7923cb1576ac5859ba4b9a16ab22eb8f8a96e78e2e961 ;; \
      *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && curl -fsSL --retry 5 --retry-all-errors --retry-delay 2 -o /tmp/gh.tar.gz \
    "https://github.com/cli/cli/releases/download/v2.100.0/gh_2.100.0_linux_${TARGETARCH}.tar.gz" \
 && echo "${gh_sha256}  /tmp/gh.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/gh.tar.gz -C /tmp \
 && install -m 0755 \
    /tmp/gh_2.100.0_linux_${TARGETARCH}/bin/gh \
    /usr/local/bin/gh \
 && rm -rf /tmp/gh.tar.gz /tmp/gh_2.100.0_linux_${TARGETARCH} \
 && apt-get purge -y --auto-remove curl \
 && rm -rf /var/lib/apt/lists/* \
 && test "$(git --version)" = "git version 2.39.5" \
 && gh --version | grep -F "gh version 2.100.0"

COPY --from=builder /app/.venv /app/.venv
COPY config /app/config
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

CMD ["sh", "-c", "if [ \"${GG_RUNTIME_MODE:-}\" = control-plane ]; then exec python -m gg.runtime --host 0.0.0.0 --port \"${PORT:-8001}\"; fi; exec python -m gg.server --host 0.0.0.0 --port 8000"]
