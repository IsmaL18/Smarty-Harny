# Image du harness (ADR-0006) : le code y est installé, le dossier de travail est monté à l'exécution.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash git ripgrep curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /opt/harness
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# Garde de cli.main : le harness refuse de s'ouvrir hors conteneur (CA-25).
ENV HARNESS_IN_CONTAINER=1 \
    PATH="/opt/harness/.venv/bin:$PATH" \
    HOME=/tmp/harness-home

WORKDIR /workspace
ENTRYPOINT ["harness"]
