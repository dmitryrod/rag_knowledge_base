#!/usr/bin/env bash
# Выполняется на сервере (SSH из GitHub Actions или вручную).
# Требует: git remote на репозиторий, права на docker, каталог /opt/apps/knowledge.
set -euo pipefail

REPO_DIR="${DEPLOY_REPO_DIR:-/opt/apps/knowledge}"
BRANCH="${DEPLOY_BRANCH:-deploy}"
COMPOSE_FILE="${COMPOSE_COMPOSE_FILE:-docker-compose.prod.yml}"

cd "$REPO_DIR"

mkdir -p local-dist/wheels

git fetch origin --prune
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"

export COMPOSE_FILE

docker compose build
docker compose up -d --remove-orphans

echo "Deploy finished: $(date -Iseconds) commit=$(git rev-parse --short HEAD)"
