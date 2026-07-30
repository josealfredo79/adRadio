"""
Reacts to WhatsApp number quality signals from Meta — shared by the
real-time webhook (meta_incoming.py, field `phone_number_quality_update`,
which only ever carries FLAGGED/UNFLAGGED) and the Celery Beat poll of the
Graph API (tasks.poll_meta_quality_ratings), which is the only source for
the real GREEN/YELLOW/RED rating.
"""
import logging

from sqlalchemy import select

from app.models.campaign import Campaign

logger = logging.getLogger(__name__)

_BASELINE_PER_HOUR = 60
_THROTTLED_PER_HOUR = _BASELINE_PER_HOUR // 2


async def pause_active_campaigns(db, advertiser_id) -> None:
    result = await db.execute(
        select(Campaign).where(
            Campaign.advertiser_id == advertiser_id,
            Campaign.status.in_(("scheduled", "running")),
        )
    )
    campaigns = result.scalars().all()
    for campaign in campaigns:
        campaign.status = "paused"
    if campaigns:
        logger.warning(
            "[META QUALITY] Auto-paused %d campaign(s) for advertiser=%s — number flagged by Meta",
            len(campaigns), advertiser_id,
        )


async def apply_quality_signal(db, advertiser, rating: str | None, tier: str | None = None) -> None:
    """Update the advertiser's known rating/tier and react to it: RED pauses
    every active campaign, YELLOW halves the hourly send cap, GREEN restores
    the baseline cap. Any other value (e.g. Meta's "NA" for a brand-new
    number) is just recorded, no reaction."""
    if rating:
        advertiser.meta_quality_rating = rating
    if tier:
        advertiser.meta_messaging_tier = tier

    if rating == "YELLOW":
        advertiser.meta_send_throttle_per_hour = _THROTTLED_PER_HOUR
    elif rating == "GREEN":
        advertiser.meta_send_throttle_per_hour = _BASELINE_PER_HOUR

    if rating == "RED":
        await pause_active_campaigns(db, advertiser.id)

    await db.commit()
