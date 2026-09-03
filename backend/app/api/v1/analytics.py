"""Analytics endpoints — /api/v1/analytics"""
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends

logger = logging.getLogger(__name__)
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.message import Message
from app.models.campaign import Campaign
from app.models.user import User
from app.models.contact import Contact
from app.models.appointment import Appointment

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/optimal-send-time")
async def optimal_send_time(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return hourly distribution of inbound messages for this advertiser.
    Higher count = more activity = better time to send.
    """
    result = await db.execute(
        select(
            func.extract("hour", Message.created_at).label("hour"),
            func.count().label("count"),
        )
        .where(
            Message.advertiser_id == current_user.id,
            Message.direction == "inbound",
        )
        .group_by(text("1"))
        .order_by(text("1"))
    )
    rows = result.all()
    if not rows:
        logger.info("No analytics data for user %s", current_user.id)

    hours_data = {int(row.hour): int(row.count) for row in rows}
    full = []
    for h in range(24):
        label = f"{h:02d}:00"
        full.append({"hour": h, "label": label, "count": hours_data.get(h, 0)})

    best_start = max(range(23), key=lambda h: hours_data.get(h, 0) + hours_data.get(h + 1, 0), default=10)
    best_label = f"{best_start:02d}:00 – {(best_start + 2):02d}:00"

    return {"hours": full, "best_window": best_label, "best_hour": best_start}


@router.get("/summary")
async def analytics_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aggregated KPIs: delivery/open/response rates, totals."""
    from app.services.analytics_service import compute_analytics_summary

    return await compute_analytics_summary(db, current_user.id)


@router.get("/campaign-performance")
async def campaign_performance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = 30,
) -> list[dict]:
    """Per-campaign stats for a specified number of days."""
    uid = current_user.id
    since = datetime.now(timezone.utc) - timedelta(days=days)

    campaigns = await db.execute(
        select(Campaign).where(
            Campaign.advertiser_id == uid,
            Campaign.created_at >= since,
        ).order_by(Campaign.created_at.desc())
    )
    campaigns = campaigns.scalars().all()

    from app.services.campaign_stats_service import compute_campaign_stats, merge_stats
    derived = await compute_campaign_stats(db, [c.id for c in campaigns])

    result = []
    for c in campaigns:
        msg_counts = await db.execute(
            select(Message.status, func.count(Message.id))
            .where(
                Message.campaign_id == c.id,
            )
            .group_by(Message.status)
        )
        statuses = {row[0]: row[1] for row in msg_counts}
        stats = merge_stats(c.stats, derived.get(c.id))
        sent = stats.get("sent", 0) or 0
        result.append({
            "campaign_id": str(c.id),
            "name": c.name,
            "type": c.type,
            "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "stats": stats,
            "breakdown": statuses,
            "delivery_rate": round(stats.get("delivered", 0) / sent * 100, 1) if sent else 0.0,
            "read_rate": round(stats.get("read", 0) / sent * 100, 1) if sent else 0.0,
        })

    return result


@router.get("/trends")
async def analytics_trends(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = 30,
) -> dict:
    """Daily outbound message counts for the last N days (chart data)."""
    uid = current_user.id
    since = datetime.now(timezone.utc) - timedelta(days=days - 1)

    rows = await db.execute(
        select(
            func.date(Message.created_at).label("day"),
            func.count().label("mensajes"),
        ).where(
            Message.advertiser_id == uid,
            Message.direction == "outbound",
            Message.created_at >= since,
        ).group_by(
            func.date(Message.created_at),
        ).order_by(
            func.date(Message.created_at),
        )
    )

    counts_map = {}
    for row in rows:
        counts_map[row.day.isoformat()] = row.mensajes

    days_out = []
    for i in range(days):
        day = (since + timedelta(days=i))
        day_str = day.date().isoformat()
        days_out.append({
            "day": day.strftime("%a"),
            "date": day_str,
            "mensajes": counts_map.get(day_str, 0),
        })

    return {"days": days_out, "total": sum(counts_map.values())}


@router.get("/top-contacts")
async def top_contacts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 10,
) -> list[dict]:
    """Contacts with the most interactions (inbound+outbound)."""
    uid = current_user.id

    rows = (await db.execute(
        select(
            Message.contact_id,
            func.count().label("total"),
        ).where(
            Message.advertiser_id == uid,
            Message.contact_id.isnot(None),
        ).group_by(
            Message.contact_id,
        ).order_by(
            func.count().desc(),
        ).limit(limit)
    )).all()

    contact_ids = [row.contact_id for row in rows]
    if not contact_ids:
        return []

    contacts = await db.execute(
        select(Contact).where(Contact.id.in_(contact_ids))
    )
    contact_map = {c.id: c for c in contacts.scalars().all()}

    result = []
    for row in rows:
        c = contact_map.get(row.contact_id)
        result.append({
            "contact_id": str(row.contact_id),
            "name": c.name if c else "Unknown",
            "phone": c.phone if c else "",
            "total_messages": row.total,
        })

    return result
