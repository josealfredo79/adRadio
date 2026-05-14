#!/bin/bash
set -e

case "${SERVICE_ROLE:-api}" in
  worker)
    echo "Starting Celery worker (all queues)..."
    exec celery -A app.workers.celery_app worker --loglevel=info --concurrency=4 -Q celery,whatsapp,processing,campaigns
    ;;
  beat)
    echo "Starting Celery beat..."
    exec celery -A app.workers.celery_app beat --loglevel=info
    ;;
  *)
    echo "Running database migrations..."
    alembic upgrade head || echo "⚠️  Migration warning (may already be up to date) — continuing..."
    echo "Starting API server on port ${PORT:-8000}..."
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 2
    ;;
esac
