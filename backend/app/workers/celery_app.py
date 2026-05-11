"""
Celery application configuration.
"""
from celery import Celery

from app.config import settings

celery_app = Celery(
    "iaradio",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # prevent duplicate processing
    task_routes={
        "app.workers.tasks.send_whatsapp_message": {"queue": "whatsapp"},
        "app.workers.tasks.process_knowledge_base_file": {"queue": "processing"},
        "app.workers.tasks.import_contacts_csv": {"queue": "processing"},
        "app.workers.tasks.schedule_campaign": {"queue": "campaigns"},
    },
)

# Celery Beat schedule
celery_app.conf.beat_schedule = {
    "check-scheduled-campaigns": {
        "task": "app.workers.tasks.check_scheduled_campaigns",
        "schedule": 60.0,  # every minute
    },
    "cleanup-expired-tokens": {
        "task": "app.workers.tasks.cleanup_expired_data",
        "schedule": 3600.0,  # every hour
    },
}
