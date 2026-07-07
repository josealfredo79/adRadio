"""
Common utilities for Celery tasks.
"""
import asyncio
import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Twilio error codes that indicate permanent failures — contact should be suppressed
_PERMANENT_ERRORS = {"63004", "63007", "63016"}


def run_async(coro):
    """Helper to run async code in sync Celery task."""
    async def _wrapped():
        try:
            return await coro
        finally:
            from app.database import _get_celery_engine
            await _get_celery_engine().dispose()
    return asyncio.run(_wrapped())


async def _get_advertiser_whatsapp_number(db: AsyncSession, advertiser_id: uuid.UUID) -> str | None:
    from app.models.user import User
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == advertiser_id))
    advertiser = result.scalar_one_or_none()
    return advertiser.whatsapp_number if advertiser else None


async def suppress_contact_on_error(db: AsyncSession, contact_id: uuid.UUID, error_code: str | None) -> None:
    """Auto-suppress contact on permanent Twilio delivery errors.

    - 63004 (invalid number) → blocked
    - 63007 (user opted out) → unsubscribed
    - 63016 (blocked number) → blocked
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

    if code == "63007":
        contact.status = "unsubscribed"
        reason = "opted_out"
    else:
        contact.status = "blocked"
        reason = "invalid_number" if code == "63004" else "blocked_by_user"

    contact.failed_send_count = (contact.failed_send_count or 0) + 1
    if (contact.failed_send_count or 0) >= 3:
        contact.suppressed_until = datetime.now(timezone.utc) + timedelta(days=30)

    logger.info("[ANTI-SPAM] Contact %s suppressed: status=%s reason=%s error=%s",
                contact_id, contact.status, reason, code)
