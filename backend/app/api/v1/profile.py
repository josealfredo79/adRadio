"""
Profile & Dashboard router — /api/v1/me, /api/v1/dashboard
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis as AsyncRedis
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, check_feature_access
from app.api.idempotency import idempotent_post, store_idempotency_response
from app.core.redis import get_redis_optional
from app.database import get_db
from app.models.automation import AutomationFlow
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.message import Message
from app.models.order import Order
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.profile import ProfileUpdate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["profile"])


class WhiteLabelOut(BaseModel):
    primary_color: str = "#6366f1"
    app_name: str = ""
    hide_branding: bool = False
    custom_domain: str = ""
    favicon_url: str = ""


class WhiteLabelUpdate(BaseModel):
    primary_color: str | None = None
    app_name: str | None = None
    hide_branding: bool | None = None
    custom_domain: str | None = None
    favicon_url: str | None = None


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


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


@router.post("/me/change-password")
async def change_password(
    request: Request,
    body: ChangePasswordBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(idempotent_post),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict[str, str]:
    """Change the current user's password after verifying the old one."""
    from app.core.security import verify_password, hash_password

    current_pw = body.current_password.strip()
    new_pw = body.new_password.strip()

    if not current_pw or not new_pw:
        raise HTTPException(status_code=400, detail="Debes proporcionar la contraseña actual y la nueva")
    if len(new_pw) < 8:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 8 caracteres")
    if not verify_password(current_pw, current_user.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")

    current_user.password_hash = hash_password(new_pw)
    await db.commit()
    logger.info("Password changed for user %s", current_user.id)
    out: dict[str, str] = {"message": "Contraseña actualizada correctamente"}
    await store_idempotency_response(request, redis, out)
    return out


@router.get("/dashboard")
async def dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis_optional),
):
    if redis:
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
    # Active automations
    automations_active = await db.execute(
        select(func.count()).where(
            AutomationFlow.advertiser_id == current_user.id,
            AutomationFlow.is_active == True,
        )
    )

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

    # Leads del bot — contactos creados vía WhatsApp este mes
    leads_from_bot = await db.execute(
        select(func.count()).where(
            Contact.advertiser_id == current_user.id,
            Contact.source == "landing",
            Contact.created_at >= first_of_month,
        )
    )
    # Solicitudes de plan (órdenes en plan_pending_confirmation)
    plan_requests = await db.execute(
        select(func.count()).where(
            Order.advertiser_id == current_user.id,
            Order.state == "plan_pending_confirmation",
        )
    )
    # Leads sin respuesta — contactos cuya última interacción fue inbound sin reply
    last_in = (
        select(
            Message.contact_id,
            Message.direction,
            func.row_number().over(
                partition_by=Message.contact_id,
                order_by=Message.created_at.desc(),
            ).label("rn"),
        )
        .where(
            Message.advertiser_id == current_user.id,
            Message.created_at >= first_of_month,
        )
        .subquery()
    )
    unreplied = await db.execute(
        select(func.count()).select_from(
            select(last_in.c.contact_id)
            .where(last_in.c.rn == 1, last_in.c.direction == "inbound")
            .subquery()
        )
    )

    data = {
        "contacts_total": contacts_total.scalar_one(),
        "campaigns_active": campaigns_active.scalar_one(),
        "automations_active": automations_active.scalar_one(),
        "messages_sent_this_month": messages_sent.scalar_one(),
        "messages_remaining": current_user.messages_remaining,
        "plan": current_user.current_plan,
        "subscription_status": current_user.subscription_status,
        "orders_confirmed": orders_confirmed.scalar_one(),
        "orders_pending": orders_pending.scalar_one(),
        "leads_from_bot": leads_from_bot.scalar_one(),
        "plan_requests": plan_requests.scalar_one(),
        "leads_unreplied": unreplied.scalar_one(),
    }

    if redis:
        await redis.setex(cache_key, 120, json.dumps(data))  # cache 2 min
    return data


@router.get("/dashboard/chart")
async def dashboard_chart(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis_optional),
):
    """Returns outbound message counts for the last 7 days."""
    from datetime import datetime, timezone, timedelta

    if redis:
        cache_key = f"dashboard_chart:{current_user.id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

    now = datetime.now(timezone.utc)
    seven_days_ago = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)

    rows = await db.execute(
        select(
            func.date(Message.created_at).label("day"),
            func.count().label("mensajes"),
        ).where(
            Message.advertiser_id == current_user.id,
            Message.direction == "outbound",
            Message.created_at >= seven_days_ago,
        ).group_by(
            func.date(Message.created_at),
        ).order_by(
            func.date(Message.created_at),
        )
    )

    counts_map: dict[str, int] = {}
    for row in rows:
        counts_map[row.day.isoformat()] = row.mensajes

    days = []
    for i in range(7):
        day = (seven_days_ago + timedelta(days=i))
        day_str = day.date().isoformat()
        days.append({
            "day": day.strftime("%a"),
            "mensajes": counts_map.get(day_str, 0),
            "date": day_str,
        })

    if redis:
        await redis.setex(cache_key, 120, json.dumps(days))
    return days


@router.get("/profile/white-label", response_model=WhiteLabelOut)
async def get_white_label(
    current_user: User = Depends(get_current_user),
):
    if not check_feature_access(current_user, "white_label"):
        raise HTTPException(status_code=402, detail="Tu plan no incluye white-label. Actualiza a Enterprise.")
    wl = current_user.white_label or {}
    return WhiteLabelOut(**wl)


@router.patch("/profile/white-label", response_model=WhiteLabelOut)
async def update_white_label(
    body: WhiteLabelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not check_feature_access(current_user, "white_label"):
        raise HTTPException(status_code=402, detail="Tu plan no incluye white-label. Actualiza a Enterprise.")
    wl = dict(current_user.white_label or {})
    for field, value in body.model_dump(exclude_none=True).items():
        wl[field] = value
    current_user.white_label = wl
    await db.commit()
    await db.refresh(current_user)
    return WhiteLabelOut(**current_user.white_label)
