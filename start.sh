#!/bin/bash
set -e

echo "=== IaRadio Startup ==="
echo "PID: $$"
echo "PORT: ${PORT:-8000}"
echo "SERVICE_ROLE: ${SERVICE_ROLE:-api}"
echo "======================="

# Railway pone un proxy delante: sin confiar en sus X-Forwarded-For, todos
# los visitantes llegan con la IP del proxy y los límites por IP (slowapi,
# p. ej. la demo de voz de la landing) serían uno solo para todo el mundo.
# El proxy de Railway es la única entrada al contenedor.
if [ "${SERVICE_ROLE:-api}" = "api" ] && [ "${SKIP_MIGRATIONS:-false}" = "true" ]; then
    # Escape de emergencia: con la BD caída (p. ej. cuota de Neon agotada)
    # alembic aborta el arranque y tumba también el landing y las páginas
    # públicas, que no necesitan BD. Quitar la variable en cuanto la BD vuelva.
    echo "WARNING: SKIP_MIGRATIONS=true — starting without running migrations"
    exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'

elif [ "${SERVICE_ROLE:-api}" = "api" ]; then
    echo "Running database migrations..."
    alembic upgrade head
    MIGRATION_EXIT=$?
    if [ $MIGRATION_EXIT -ne 0 ]; then
        echo "CRITICAL: Database migration failed (exit=$MIGRATION_EXIT). Aborting."
        exit $MIGRATION_EXIT
    fi
    echo "Migrations applied successfully"

    # NOTE: Celery worker and beat are managed as dedicated Railway services
    # (Dockerfile.worker). Do NOT start them inline here to avoid duplicate
    # Beat schedulers sending double messages to customers.

    echo "Starting Uvicorn..."
    exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'

elif [ "${SERVICE_ROLE}" = "worker" ]; then
    exec celery -A app.workers.celery_app worker \
        --loglevel=info \
        -Q whatsapp,campaigns,processing \
        --pool threads -c 4

elif [ "${SERVICE_ROLE}" = "beat" ]; then
    exec celery -A app.workers.celery_app beat --loglevel=info

else
    echo "Unknown SERVICE_ROLE: ${SERVICE_ROLE}"
    exit 1
fi