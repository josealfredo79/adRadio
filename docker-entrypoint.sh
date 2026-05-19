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
  worker-beat)
    # ── Modo combinado: Worker + Beat en un solo contenedor ────────────────
    # Ahorra un servicio completo en Railway (~$8-12/mes).
    # Usar cuando el volumen de tareas no justifica 2 contenedores separados.
    # Si Beat cae, el Worker también cae — Railway lo reiniciará automáticamente.
    echo "Starting Celery worker + beat (combined mode)..."
    exec celery -A app.workers.celery_app worker --beat --loglevel=info --concurrency=2 -Q celery,whatsapp,processing,campaigns
    ;;
  *)
    echo "Running migrations..."
    alembic upgrade head || echo "Migrations done (or skipped)"
    
    PORT_VALUE=${PORT:-8000}
    echo "Starting uvicorn on port $PORT_VALUE..."
    exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT_VALUE"
    ;;
esac
