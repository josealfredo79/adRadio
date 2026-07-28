"""
Common utilities for Celery tasks.
"""
import asyncio
import logging
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# WhatsApp Cloud API (Meta) error codes that indicate a permanent delivery
# failure — contact should be suppressed. Source: Meta's official error code
# reference (developers.facebook.com/.../whatsapp/support/error-codes).
#
# Meta deliberately does NOT distinguish "user blocked us" from "not on
# WhatsApp" from "opted out" — all of these collapse into one generic
# undeliverable code for privacy reasons, unlike Twilio's separate
# 63004/63007/63016. So there's no way to pick a specific `status`/`reason`
# the way the old Twilio-code mapping did; every hit here is just "stop
# messaging this number."
_PERMANENT_ERRORS = {"131026"}


def run_async(coro):
    """Helper to run async code in sync Celery task."""
    async def _wrapped():
        try:
            return await coro
        finally:
            from app.database import _get_celery_engine
            await _get_celery_engine().dispose()
    return asyncio.run(_wrapped())


async def suppress_contact_on_error(db: AsyncSession, contact_id: uuid.UUID, error_code: str | None) -> None:
    """Auto-suppress contact on a permanent WhatsApp delivery error.

    131026 = Meta's "unable to deliver" — recipient not on WhatsApp, hasn't
    accepted ToS, or has blocked the business. Meta doesn't disclose which.
    """
    if not error_code:
        return
    code = str(error_code).strip()
    if code not in _PERMANENT_ERRORS:
        return

    from app.models.contact import Contact
    from datetime import datetime, timezone, timedelta

    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    contact = result.scalar_one_or_none()
    if not contact:
        return

    contact.status = "blocked"
    contact.failed_send_count = (contact.failed_send_count or 0) + 1
    if (contact.failed_send_count or 0) >= 3:
        contact.suppressed_until = datetime.now(timezone.utc) + timedelta(days=30)

    logger.info("[ANTI-SPAM] Contact %s suppressed: status=blocked error=%s",
                contact_id, code)
