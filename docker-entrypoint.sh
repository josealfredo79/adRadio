#!/bin/bash
set -e

echo "=== Railway Debug ==="
echo "PORT: ${PORT}"
echo "=================="

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
    alembic upgrade head || echo "Migrations done (or skipped)"
    
    PORT_VALUE=${PORT:-8000}
    echo "Starting uvicorn on port $PORT_VALUE..."
    exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT_VALUE"
    ;;
esac
