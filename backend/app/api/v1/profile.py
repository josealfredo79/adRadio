"""
Profile & Dashboard router — /api/v1/me, /api/v1/dashboard
"""
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.config import settings
from app.core.redis import get_redis
from app.database import get_db
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.message import Message
from app.models.user import User
from app.schemas.auth import UserOut

router = APIRouter(tags=["profile"])


@router.get("/me", response_model=UserOut)
async def get_profile(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.patch("/me", response_model=UserOut)
async def update_profile(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed_fields = {
        "business_name", "business_category", "city", "country",
        "phone", "whatsapp_number", "language", "bot_personality", "bot_name",
    }
    for field, value in body.items():
        if field in allowed_fields:
            setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return UserOut.model_validate(current_user)


@router.get("/dashboard")
async def dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis),
):
    cache_key = f"dashboard:{current_user.id}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # Contacts count
    contacts_total = await db.execute(
        select(func.count()).where(
            Contact.advertiser_id == current_user.id,
            Contact.status == "active",
        )
    )

    # Campaigns active
    campaigns_active = await db.execute(
        select(func.count()).where(
            Campaign.advertiser_id == current_user.id,
            Campaign.status.in_(["running", "scheduled"]),
        )
    )

    # Messages sent this month
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    messages_sent = await db.execute(
        select(func.count()).where(
            Message.advertiser_id == current_user.id,
            Message.direction == "outbound",
            Message.created_at >= first_of_month,
        )
    )

    data = {
        "contacts_total": contacts_total.scalar_one(),
        "campaigns_active": campaigns_active.scalar_one(),
        "messages_sent_this_month": messages_sent.scalar_one(),
        "messages_remaining": current_user.messages_remaining,
        "plan": current_user.current_plan,
        "subscription_status": current_user.subscription_status,
    }

    await redis.setex(cache_key, 300, json.dumps(data))  # cache 5 min
    return data


@router.get("/dashboard/chart")
async def dashboard_chart(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis),
):
    """Returns outbound message counts for the last 7 days."""
    from datetime import datetime, timezone, timedelta

    cache_key = f"dashboard_chart:{current_user.id}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    now = datetime.now(timezone.utc)
    days = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        count_result = await db.execute(
            select(func.count()).where(
                Message.advertiser_id == current_user.id,
                Message.direction == "outbound",
                Message.created_at >= day_start,
                Message.created_at < day_end,
            )
        )
        count = count_result.scalar_one()
        days.append({
            "day": day_start.strftime("%a"),
            "mensajes": count,
            "date": day_start.date().isoformat(),
        })

    await redis.setex(cache_key, 300, json.dumps(days))
    return days


# ---------------------------------------------------------------------------
# Admin: number pool management
# ---------------------------------------------------------------------------

@router.get("/admin/number-pool")
async def list_number_pool(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List all numbers in the pool and their assignment status."""
    pool = settings.twilio_number_pool_list
    if not pool:
        return {"pool": [], "available": [], "assigned": []}

    # Find which numbers are already assigned
    result = await db.execute(
        select(User.whatsapp_number, User.email, User.business_name).where(
            User.whatsapp_number_source == "pool",
            User.whatsapp_number.in_(pool),
        )
    )
    assigned_rows = result.all()
    assigned_map = {row.whatsapp_number: {"email": row.email, "business": row.business_name}
                    for row in assigned_rows}

    available = [n for n in pool if n not in assigned_map]

    return {
        "pool": pool,
        "available": available,
        "assigned": [{"number": n, **info} for n, info in assigned_map.items()],
    }


@router.post("/admin/users/{user_id}/assign-number")
async def assign_number_to_user(
    user_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Assign a dedicated WhatsApp number to a user.
    body: { "number": "+525511111111" }   → assigns specific number
    body: { "auto": true }                → picks next available from pool
    body: { "release": true }             → releases back to pool
    """
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if body.get("release"):
        user.whatsapp_number = None
        user.whatsapp_number_source = "shared"
        await db.commit()
        return {"message": "Número liberado — vuelve al número compartido"}

    pool = settings.twilio_number_pool_list
    if not pool:
        raise HTTPException(status_code=503, detail="Pool de números no configurado (TWILIO_NUMBER_POOL)")

    if body.get("auto"):
        # Find first unassigned number
        result2 = await db.execute(
            select(User.whatsapp_number).where(
                User.whatsapp_number_source == "pool",
                User.whatsapp_number.in_(pool),
            )
        )
        taken = {row[0] for row in result2.all()}
        available = [n for n in pool if n not in taken]
        if not available:
            raise HTTPException(status_code=409, detail="No hay números disponibles en el pool")
        number = available[0]
    else:
        number = body.get("number", "").strip()
        if number not in pool:
            raise HTTPException(status_code=400, detail=f"{number} no está en TWILIO_NUMBER_POOL")

    user.whatsapp_number = number
    user.whatsapp_number_source = "pool"
    await db.commit()
    return {"message": f"Número {number} asignado a {user.email}", "number": number}
