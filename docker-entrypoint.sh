#!/bin/bash
set -e

echo "=== DEBUG: PORT = ${PORT} ==="

case "${SERVICE_ROLE:-api}" in
  worker)
    echo "Starting Celery worker..."
    exec celery -A app.workers.celery_app worker --loglevel=info --concurrency=2 -Q celery,whatsapp,processing,campaigns
    ;;
  beat)
    echo "Starting Celery beat..."
    exec celery -A app.workers.celery_app beat --loglevel=info
    ;;
  *)
    echo "Running migrations..."
    alembic upgrade head || true
    
    echo "Starting uvicorn on port ${PORT:-8000}..."
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
    ;;
esac
