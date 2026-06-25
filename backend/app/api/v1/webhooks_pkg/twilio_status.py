"""
Twilio status callback webhook — update message delivery status.
"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.campaign import Campaign
from app.models.message import Message
from app.core.rate_limiter import limiter

logger = logging.getLogger(__name__)


@limiter.limit("60/minute")
async def twilio_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Update message delivery status from Twilio callbacks."""
    form_data = dict(await request.form())
    twilio_sid = form_data.get("MessageSid")
    msg_status = form_data.get("MessageStatus")

    if twilio_sid and msg_status:
        result = await db.execute(
            select(Message).where(Message.twilio_sid == twilio_sid)
        )
        msg = result.scalar_one_or_none()
        if msg:
            from datetime import datetime, timezone
            status_map = {
                "sent": "sent",
                "delivered": "delivered",
                "read": "read",
                "failed": "failed",
                "undelivered": "failed",
            }
            new_status = status_map.get(msg_status, msg.status)
            old_status = msg.status
            msg.status = new_status

            now = datetime.now(timezone.utc)
            if new_status == "delivered" and not msg.delivered_at:
                msg.delivered_at = now
            elif new_status == "read" and not msg.read_at:
                msg.read_at = now

            if msg.campaign_id and new_status != old_status:
                camp_result = await db.execute(
                    select(Campaign).where(Campaign.id == msg.campaign_id)
                )
                campaign = camp_result.scalar_one_or_none()
                if campaign:
                    stats = dict(campaign.stats)
                    if new_status == "sent":
                        stats["sent"] = stats.get("sent", 0) + 1
                    elif new_status == "delivered":
                        stats["delivered"] = stats.get("delivered", 0) + 1
                    elif new_status == "read":
                        stats["read"] = stats.get("read", 0) + 1
                    elif new_status == "failed":
                        stats["failed"] = stats.get("failed", 0) + 1
                    campaign.stats = stats

            await db.commit()

    return {"message": "ok"}
