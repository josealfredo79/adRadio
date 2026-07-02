#!/bin/bash
set -e

echo "=== IaRadio Startup ==="
echo "PID: $$"
echo "PORT: ${PORT:-8000}"
echo "SERVICE_ROLE: ${SERVICE_ROLE:-api}"
echo "======================="

if [ "${SERVICE_ROLE:-api}" = "api" ]; then
    echo "Running database migrations..."
    alembic upgrade head
    MIGRATION_EXIT=$?
    if [ $MIGRATION_EXIT -ne 0 ]; then
        echo "CRITICAL: Database migration failed (exit=$MIGRATION_EXIT). Aborting."
        exit $MIGRATION_EXIT
    fi
    echo "Migrations applied successfully"

    echo "Starting Celery worker (background)..."
    celery -A app.workers.celery_app worker \
        --loglevel=info \
        -Q whatsapp,campaigns,processing \
        --pool threads -c 1 &
    CELERY_WORKER_PID=$!
    echo "Celery worker started (PID: $CELERY_WORKER_PID)"

    echo "Starting Celery beat (background)..."
    celery -A app.workers.celery_app beat \
        --loglevel=info &
    CELERY_BEAT_PID=$!
    echo "Celery beat started (PID: $CELERY_BEAT_PID)"

    echo "Starting Uvicorn..."
    exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}

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