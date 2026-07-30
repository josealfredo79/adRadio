"""
Helper utilities for Celery tasks.
"""
from app.workers.task_helpers.common import run_async, suppress_contact_on_error
from app.workers.task_helpers.extract import _extract_text
from app.workers.task_helpers.campaign_ops import (
    send_regular_messages, send_banner_messages, send_radio_messages,
    send_parrilla_messages, notify_campaign_failed, run_parrilla_generation,
    segment_fingerprint, is_segment_on_cooldown, record_segment_send,
)
from app.workers.task_helpers.appointment_ops import (
    send_24h_reminders, send_1h_reminders,
)
