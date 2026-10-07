#!/usr/bin/env bash
# Corre la suite del backend contra Postgres y Redis locales en Docker (nunca
# contra Neon ni producción). Uso, desde backend/:  scripts/test_local.sh [args de pytest]
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env.test ] || cp .env.test.example .env.test

# Base nueva en cada corrida: algunos tests dejan datos y la siguiente corrida
# los vería (ej. un "número desconocido" que ya existe).
docker rm -f adradio-test-pg >/dev/null 2>&1 || true
docker run -d --name adradio-test-pg -e POSTGRES_PASSWORD=pg -e POSTGRES_DB=adradio -p 55432:5432 pgvector/pgvector:pg16 >/dev/null
if ! docker ps --format '{{.Names}}' | grep -qx adradio-test-redis; then
  docker rm -f adradio-test-redis >/dev/null 2>&1 || true
  docker run -d --name adradio-test-redis -p 56379:6379 redis:7-alpine >/dev/null
fi
until docker exec adradio-test-pg pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done

# Las mismas variables que .env.test, para alembic (que no pasa por conftest),
# y sin leer el .env de producción.
set -a; . ./.env.test; set +a
export APP_ENV_FILE=""
alembic upgrade head >/dev/null
exec python -m pytest tests/ -q -p no:cacheprovider "$@"
