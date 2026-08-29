"""
Celery application configuration.
"""
from celery import Celery

from app.config import settings

# Force model loading so SQLAlchemy mappers resolve all relationships (e.g. User → KnowledgeBase)
import app.models  # noqa: F401

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
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # prevent duplicate processing
    task_soft_time_limit=300,    # 5 min soft limit
    task_time_limit=600,         # 10 min hard limit
    worker_max_tasks_per_child=1000,  # prevent memory leak
    task_routes={
        "app.workers.tasks.send_whatsapp_message": {"queue": "whatsapp"},
        "app.workers.tasks.process_knowledge_base_file": {"queue": "processing"},
        "app.workers.tasks.import_contacts_csv": {"queue": "processing"},
        "app.workers.tasks.schedule_campaign": {"queue": "campaigns"},
        "app.workers.tasks.generate_parrilla_task": {"queue": "campaigns"},
        "app.workers.tasks.run_lab_task": {"queue": "processing"},
    },
)

# Celery Beat schedule
celery_app.conf.beat_schedule = {
    "check-scheduled-campaigns": {
        "task": "app.workers.tasks.check_scheduled_campaigns",
        "schedule": 300.0,  # every 5 minutes — sufficient for campaign scheduling
    },
    "cleanup-expired-tokens": {
        "task": "app.workers.tasks.cleanup_expired_data",
        "schedule": 3600.0,  # every hour
    },
    "replenish-annual-message-quota": {
        "task": "app.workers.tasks.replenish_annual_message_quota",
        "schedule": 3600.0,  # every hour — messages_refill_at is date-precision, hourly is plenty
    },
    "send-appointment-reminders": {
        "task": "app.workers.tasks.send_appointment_reminders",
        "schedule": 300.0,  # every 5 minutes
    },
    "send-closer-reminders": {
        "task": "app.workers.tasks.send_closer_reminders_task",
        "schedule": 300.0,  # every 5 minutes — offers are short-lived (hours)
    },
    "process-automation-enrollments": {
        "task": "app.workers.tasks.process_automation_enrollments",
        "schedule": 60.0,  # every minute — drip messages precision
    },
    "send-trial-expiry-reminders": {
        "task": "app.workers.tasks.send_trial_expiry_reminders",
        "schedule": 43200.0,  # every 12 hours — enough for daily reminders
    },
    "poll-meta-quality-ratings": {
        "task": "app.workers.tasks.poll_meta_quality_ratings",
        "schedule": 1800.0,  # every 30 minutes — catches YELLOW before Meta fully flags the number
    },
}
