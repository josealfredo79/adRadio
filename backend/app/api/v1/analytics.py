"""Analytics endpoints — /api/v1/analytics"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.message import Message
from app.models.user import User

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/optimal-send-time")
async def optimal_send_time(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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

    hours_data = {int(row.hour): int(row.count) for row in rows}
    full = []
    for h in range(24):
        label = f"{h:02d}:00"
        full.append({"hour": h, "label": label, "count": hours_data.get(h, 0)})

    # Find best window (max consecutive 2-hour block)
    best_start = max(range(23), key=lambda h: hours_data.get(h, 0) + hours_data.get(h + 1, 0), default=10)
    best_label = f"{best_start:02d}:00 – {(best_start + 2):02d}:00"

    return {"hours": full, "best_window": best_label, "best_hour": best_start}
