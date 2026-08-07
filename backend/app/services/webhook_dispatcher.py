"""
Webhook dispatcher — sends event notifications to active user webhooks.
"""
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_webhook import UserWebhook

logger = logging.getLogger(__name__)


def _sign_body(secret: str, body: bytes) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


async def dispatch_webhook_event(
    event: str,
    payload: dict,
    db: AsyncSession,
    advertiser_id: uuid.UUID,
) -> None:
    """Query *advertiser_id*'s own active webhooks subscribed to *event* and POST
    the payload concurrently. advertiser_id is required — without it this would
    broadcast one advertiser's event to every other advertiser's webhooks."""
    result = await db.execute(
        select(UserWebhook).where(
            UserWebhook.user_id == advertiser_id,
            UserWebhook.active == True,  # noqa: E712
            # events is JSONB (a plain array column), not Postgres ARRAY — .any()
            # is an ARRAY-comparator method and raises AttributeError on JSONB.
            # .contains([event]) compiles to the `@>` containment operator instead.
            UserWebhook.events.contains([event]),
        )
    )
    webhooks = result.scalars().all()

    if not webhooks:
        logger.debug("[WEBHOOK-DISPATCH] No active webhooks for event=%s", event)
        return

    timestamp = datetime.now(timezone.utc).isoformat()
    body_data = {
        "event": event,
        "timestamp": timestamp,
        "data": payload,
    }
    body_bytes = json.dumps(body_data).encode("utf-8")

    async def _send(wh: UserWebhook) -> None:
        signature = _sign_body(wh.secret, body_bytes)
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": event,
            "User-Agent": "IaRadio-Webhook/1.0",
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(wh.url, content=body_bytes, headers=headers)
                resp.raise_for_status()
                logger.info(
                    "[WEBHOOK-DISPATCH] event=%s url=%s status=%d",
                    event, wh.url, resp.status_code,
                )
        except Exception as exc:
            logger.error(
                "[WEBHOOK-DISPATCH] FAILED event=%s url=%s error=%s",
                event, wh.url, exc,
            )

    import asyncio
    await asyncio.gather(*[_send(wh) for wh in webhooks], return_exceptions=True)
