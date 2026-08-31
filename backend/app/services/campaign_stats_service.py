"""Derive campaign engagement stats from the source-of-truth tables
(``messages`` + ``coupons``) instead of hand-maintained JSON counters on
``Campaign.stats``.

Those counters drifted: ``send_whatsapp_message`` never bumped ``sent``,
while every WhatsApp delivery-status webhook did ``stats[x] += 1`` with no
dedupe and no decrement of the previous bucket. WhatsApp resends and
reorders those receipts routinely, so a campaign ended up with
``delivered`` > ``sent`` (an 800% delivery rate in the UI) and a
``failed`` count for messages that later succeeded on retry.

Recomputing from ``messages.status`` on every read is cheap (one grouped
count per request) and always consistent with the per-contact breakdown
the campaign card already shows.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coupon import Coupon
from app.models.message import Message

# WhatsApp's delivery funnel is monotonic: a "read" receipt implies the
# message was delivered, which implies it was sent. We collapse the raw
# per-status row counts back into that funnel so each stage is a superset
# of the next and a rate can never exceed 100%.
_DELIVERED_STATUSES = ("delivered", "read")
_SENT_STATUSES = ("sent", "delivered", "read")


async def compute_campaign_stats(
    db: AsyncSession, campaign_ids: list,
) -> dict:
    """Return ``{campaign_id: {queued, sent, delivered, read, failed,
    coupons_redeemed}}`` derived live from the messages/coupons tables.

    ``replied`` is intentionally left to the caller to merge from the
    stored JSON (it is not tracked per-campaign on inbound messages).
    """
    if not campaign_ids:
        return {}

    rows = await db.execute(
        select(Message.campaign_id, Message.status, func.count(Message.id))
        .where(
            Message.campaign_id.in_(campaign_ids),
            Message.direction == "outbound",
        )
        .group_by(Message.campaign_id, Message.status)
    )
    raw: dict = {}
    for cid, status, cnt in rows:
        raw.setdefault(cid, {})[status] = cnt

    coupon_rows = await db.execute(
        select(Coupon.campaign_id, func.count(Coupon.id))
        .where(
            Coupon.campaign_id.in_(campaign_ids),
            Coupon.redeemed_at.isnot(None),
        )
        .group_by(Coupon.campaign_id)
    )
    redeemed = {cid: cnt for cid, cnt in coupon_rows}

    out: dict = {}
    for cid in campaign_ids:
        s = raw.get(cid, {})
        out[cid] = {
            "queued": s.get("queued", 0),
            "sent": sum(s.get(x, 0) for x in _SENT_STATUSES),
            "delivered": sum(s.get(x, 0) for x in _DELIVERED_STATUSES),
            "read": s.get("read", 0),
            "failed": s.get("failed", 0),
            "coupons_redeemed": redeemed.get(cid, 0),
        }
    return out


def merge_stats(stored: dict | None, derived: dict | None) -> dict:
    """Overlay derived engagement counts on top of the stored JSON so
    fields we don't recompute (``replied``) still pass through."""
    merged = dict(stored or {})
    merged.update(derived or {})
    return merged
