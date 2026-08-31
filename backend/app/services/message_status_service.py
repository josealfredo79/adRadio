"""
Apply a WhatsApp delivery status update to a Message + its campaign stats.

Extracted from twilio_status.py so the Meta webhook (whose message and
status events arrive in the same payload, not a separate callback URL like
Twilio's) can reuse the same mapping logic.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.services.realtime import publish_conversation_event

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    "sent": "sent",
    "delivered": "delivered",
    "read": "read",
    "failed": "failed",
}


async def apply_status_update(
    db: AsyncSession,
    wa_message_id: str,
    wa_status: str,
    error_code: str | None = None,
) -> None:
    if not wa_message_id or not wa_status:
        return

    result = await db.execute(select(Message).where(Message.wa_message_id == wa_message_id))
    msg = result.scalar_one_or_none()
    if not msg:
        return

    new_status = _STATUS_MAP.get(wa_status, msg.status)
    old_status = msg.status
    msg.status = new_status
    if error_code:
        msg.error_code = error_code

    now = datetime.now(timezone.utc)
    if new_status == "delivered" and not msg.delivered_at:
        msg.delivered_at = now
    elif new_status == "read" and not msg.read_at:
        msg.read_at = now

    # Campaign engagement stats are derived live from messages.status on
    # read (see campaign_stats_service) — we deliberately do NOT bump a
    # Campaign.stats counter here. WhatsApp resends/reorders these status
    # receipts, and the old "stats[new_status] += 1" had no dedupe and
    # never decremented the prior bucket, so delivered/read drifted above
    # sent and produced a >100% delivery rate in the UI.

    await db.commit()
    if msg.contact_id:
        await publish_conversation_event(msg.advertiser_id, {"type": "status", "contact_id": str(msg.contact_id)})
