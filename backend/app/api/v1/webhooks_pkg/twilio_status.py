"""
Twilio status callback webhook — update message delivery status.
"""
import hashlib
import hmac
import logging
from fastapi import HTTPException, status

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.campaign import Campaign
from app.models.message import Message
from app.core.rate_limiter import limiter

logger = logging.getLogger(__name__)


def _validate_twilio_signature(request_url: str, params: dict, signature: str) -> bool:
    """Validate X-Twilio-Signature HMAC-SHA1."""
    import base64
    sorted_params = "".join(f"{k}{v}" for k, v in sorted(params.items()))
    s = request_url + sorted_params
    mac = hmac.new(
        settings.TWILIO_AUTH_TOKEN.encode("utf-8"),
        s.encode("utf-8"),
        hashlib.sha1,
    )
    expected = base64.b64encode(mac.digest()).decode()
    return hmac.compare_digest(expected, signature)


@limiter.limit("60/minute")
async def twilio_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Update message delivery status from Twilio callbacks."""
    signature = request.headers.get("X-Twilio-Signature", "")
    form_data = dict(await request.form())

    if settings.TWILIO_AUTH_TOKEN:
        url = str(request.url)
        if signature:
            if not _validate_twilio_signature(url, form_data, signature):
                import re
                alt_url = re.sub(r"^https?://[^/]+", settings.BASE_URL, url)
                if alt_url == url or not _validate_twilio_signature(alt_url, form_data, signature):
                    logger.warning("[STATUS] Signature validation failed — url=%s", url)
                    if not settings.DEBUG:
                        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
        elif not settings.DEBUG:
            logger.warning("[STATUS] Missing X-Twilio-Signature header")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature")

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
