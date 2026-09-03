"""
PostHog analytics tracking service, plus the advertiser-facing KPI summary
(compute_analytics_summary) shared by the /analytics/summary route and the
Copiloto's get_analytics_overview tool — one query set, two callers.
"""
import logging
from typing import Any
from uuid import UUID

import posthog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.order import Order

logger = logging.getLogger(__name__)

_initialized = False


def _ensure_init():
    global _initialized
    if not _initialized and settings.POSTHOG_API_KEY:
        posthog.project_api_key = settings.POSTHOG_API_KEY
        posthog.host = "https://app.posthog.com"
        _initialized = True


def capture_event(
    event: str,
    user_id: str | UUID | None = None,
    properties: dict[str, Any] | None = None,
    distinct_id: str | None = None,
):
    if not settings.POSTHOG_API_KEY:
        return
    _ensure_init()
    try:
        pid = distinct_id or (str(user_id) if user_id else "anonymous")
        posthog.capture(
            distinct_id=pid,
            event=event,
            properties=properties or {},
        )
    except Exception:
        logger.debug("PostHog capture failed for event=%s", event, exc_info=True)


def identify_user(user_id: str | UUID, traits: dict[str, Any] | None = None):
    if not settings.POSTHOG_API_KEY:
        return
    _ensure_init()
    try:
        posthog.identify(distinct_id=str(user_id), properties=traits or {})
    except Exception:
        logger.debug("PostHog identify failed for user=%s", user_id, exc_info=True)


def flush():
    if _initialized:
        try:
            posthog.flush()
        except Exception:
            pass


async def compute_analytics_summary(db: AsyncSession, user_id: UUID) -> dict:
    """Aggregated KPIs: delivery/open/response rates, totals. Same query set
    as the /analytics/summary route — one round trip, no per-campaign loop."""
    total_out = await db.scalar(
        select(func.count()).where(Message.advertiser_id == user_id, Message.direction == "outbound")
    )
    total_in = await db.scalar(
        select(func.count()).where(Message.advertiser_id == user_id, Message.direction == "inbound")
    )
    sent = await db.scalar(
        select(func.count()).where(
            Message.advertiser_id == user_id, Message.direction == "outbound", Message.status != "queued"
        )
    )
    delivered = await db.scalar(
        select(func.count()).where(
            Message.advertiser_id == user_id, Message.direction == "outbound", Message.delivered_at.isnot(None)
        )
    )
    read = await db.scalar(
        select(func.count()).where(
            Message.advertiser_id == user_id, Message.direction == "outbound", Message.read_at.isnot(None)
        )
    )
    replied = await db.scalar(
        select(func.count()).where(Message.advertiser_id == user_id, Message.direction == "inbound")
    )
    failed = await db.scalar(
        select(func.count()).where(
            Message.advertiser_id == user_id, Message.direction == "outbound", Message.status == "failed"
        )
    )

    active_contacts = await db.scalar(
        select(func.count()).where(Contact.advertiser_id == user_id, Contact.status == "active")
    )
    total_campaigns = await db.scalar(select(func.count()).where(Campaign.advertiser_id == user_id))
    active_campaigns = await db.scalar(
        select(func.count()).where(
            Campaign.advertiser_id == user_id, Campaign.status.in_(["running", "scheduled"])
        )
    )
    orders_confirmed = await db.scalar(
        select(func.count()).where(Order.advertiser_id == user_id, Order.state == "confirmed")
    )
    conversations_active = await db.scalar(
        select(func.count()).where(Conversation.advertiser_id == user_id, Conversation.status == "active")
    )

    sent_val = sent or 0
    delivery_rate = round((delivered or 0) / sent_val * 100, 1) if sent_val > 0 else 0.0
    read_rate = round((read or 0) / sent_val * 100, 1) if sent_val > 0 else 0.0
    response_rate = round((replied or 0) / sent_val * 100, 1) if sent_val > 0 else 0.0

    return {
        "totals": {
            "messages_outbound": total_out or 0,
            "messages_inbound": total_in or 0,
            "sent": sent_val,
            "delivered": delivered or 0,
            "read": read or 0,
            "replied": replied or 0,
            "failed": failed or 0,
        },
        "rates": {
            "delivery_rate": delivery_rate,
            "read_rate": read_rate,
            "response_rate": response_rate,
        },
        "business": {
            "active_contacts": active_contacts or 0,
            "total_campaigns": total_campaigns or 0,
            "active_campaigns": active_campaigns or 0,
            "orders_confirmed": orders_confirmed or 0,
            "conversations_active": conversations_active or 0,
        },
    }
