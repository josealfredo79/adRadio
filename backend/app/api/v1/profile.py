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
from app.models.order import Order
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.profile import ProfileUpdate
from app.services.number_pool_service import assign_pool_number, release_pool_number, pool_status

router = APIRouter(tags=["profile"])


@router.get("/me", response_model=UserOut)
async def get_profile(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.patch("/me", response_model=UserOut)
async def update_profile(
    body: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return UserOut.model_validate(current_user)


@router.post("/me/change-password")
async def change_password(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change the current user's password after verifying the old one."""
    from app.core.security import verify_password, hash_password

    current_pw = (body.get("current_password") or "").strip()
    new_pw = (body.get("new_password") or "").strip()

    if not current_pw or not new_pw:
        raise HTTPException(status_code=400, detail="Debes proporcionar la contraseña actual y la nueva")
    if len(new_pw) < 8:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 8 caracteres")
    if not verify_password(current_pw, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")

    current_user.hashed_password = hash_password(new_pw)
    await db.commit()
    return {"message": "Contraseña actualizada correctamente"}


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

    # Orders confirmed (all time)
    orders_confirmed = await db.execute(
        select(func.count()).where(
            Order.advertiser_id == current_user.id,
            Order.state == "confirmed",
        )
    )
    # Orders pending (in-progress)
    orders_pending = await db.execute(
        select(func.count()).where(
            Order.advertiser_id == current_user.id,
            Order.state.notin_(["confirmed", "cancelled"]),
        )
    )

    data = {
        "contacts_total": contacts_total.scalar_one(),
        "campaigns_active": campaigns_active.scalar_one(),
        "messages_sent_this_month": messages_sent.scalar_one(),
        "messages_remaining": current_user.messages_remaining,
        "plan": current_user.current_plan,
        "subscription_status": current_user.subscription_status,
        "orders_confirmed": orders_confirmed.scalar_one(),
        "orders_pending": orders_pending.scalar_one(),
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
    return await pool_status(db)


@router.post("/admin/users/{user_id}/assign-number")
async def assign_number_to_user(
    user_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Assign/release a WhatsApp number for a user.
    body: { "auto": true }    → picks next free number from pool
    body: { "release": true } → releases number back to pool
    """
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if body.get("release"):
        await release_pool_number(user, db)
        return {"message": "Número liberado — usuario vuelve al número compartido"}

    assigned = await assign_pool_number(user, db)
    if not assigned:
        raise HTTPException(status_code=409, detail="Pool agotado o no configurado (TWILIO_NUMBER_POOL)")
    return {"message": f"Número {user.whatsapp_number} asignado a {user.email}", "number": user.whatsapp_number}
