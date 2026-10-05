"""Cuenta del cliente — /api/v1/public/me (ver customer_account.py).

El cliente entra con su número + un código por WhatsApp y ve todos los
negocios IaRadio donde es cliente; de ahí salta al portal de cada uno.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limiter import limiter
from app.core.redis import get_redis_optional
from app.database import get_db
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.user import User
from app.services.availability_service import TZ
from app.services.customer_account import (
    CodeError,
    canonical_phone,
    check_code,
    contact_phone_canonical,
    issue_code,
    make_account_token,
    read_account_token,
    send_code,
)
from app.services.loyalty_service import get_card
from app.services.portal_service import make_portal_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/me", tags=["customer-account"])

# Misma respuesta exista o no el número: no revelar quién es cliente de quién.
CODE_SENT = "Si tu número está registrado con algún negocio, te llegará un código por WhatsApp."


async def _contacts_for(db: AsyncSession, phone: str) -> list[tuple[Contact, User]]:
    rows = await db.execute(
        select(Contact, User)
        .join(User, User.id == Contact.advertiser_id)
        .where(contact_phone_canonical() == phone, Contact.status != "blocked")
        .order_by(User.business_name)
    )
    return list(rows.all())


@router.get("/status")
async def account_status() -> dict:
    return {"available": settings.CUSTOMER_ACCOUNT_ENABLED}


def _need_redis(redis: AsyncRedis | None) -> AsyncRedis:
    if redis is None:
        raise HTTPException(status_code=503, detail="Intenta de nuevo en un momento")
    return redis


@router.post("/code")
@limiter.limit("5/minute")
async def request_code(
    request: Request,
    body: dict,
    db: AsyncSession = Depends(get_db),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict:
    if not settings.CUSTOMER_ACCOUNT_ENABLED:
        raise HTTPException(status_code=503, detail="Muy pronto podrás entrar con tu número.")
    phone = canonical_phone(str(body.get("phone") or ""))
    if phone is None:
        raise HTTPException(status_code=400, detail="Escribe tu número de WhatsApp a 10 dígitos")
    redis = _need_redis(redis)
    # Solo se gasta un WhatsApp (lo cobra Meta) si de verdad es cliente de alguien.
    if not await _contacts_for(db, phone):
        return {"message": CODE_SENT}
    try:
        code = await issue_code(redis, phone)
    except CodeError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    if not await send_code(phone, code):
        raise HTTPException(status_code=503, detail="No pudimos mandarte el código. Intenta más tarde.")
    return {"message": CODE_SENT}


@router.post("/verify")
@limiter.limit("10/minute")
async def verify_code(
    request: Request,
    body: dict,
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict:
    phone = canonical_phone(str(body.get("phone") or ""))
    if phone is None or not await check_code(_need_redis(redis), phone, str(body.get("code") or "")):
        raise HTTPException(status_code=400, detail="Código incorrecto o vencido")
    return {"token": make_account_token(phone)}


@router.get("/businesses")
@limiter.limit("30/minute")
async def my_businesses(
    request: Request,
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> dict:
    phone = read_account_token(authorization.removeprefix("Bearer ").strip())
    if phone is None:
        raise HTTPException(status_code=401, detail="Vuelve a entrar con tu número")
    now = datetime.now(timezone.utc)
    out = []
    for contact, advertiser in await _contacts_for(db, phone):
        next_appt = (
            await db.execute(
                select(Appointment)
                .where(
                    Appointment.contact_id == contact.id,
                    Appointment.status.in_(("pending", "confirmed")),
                    Appointment.scheduled_at > now,
                )
                .order_by(Appointment.scheduled_at)
                .limit(1)
            )
        ).scalar_one_or_none()
        coupons = (
            await db.execute(
                select(Coupon.id).where(
                    Coupon.contact_id == contact.id,
                    Coupon.expires_at > now,
                    Coupon.used_count < Coupon.max_uses,
                )
            )
        ).scalars().all()
        out.append({
            "portal_path": f"/c/{make_portal_token(contact.id)}",
            "name": advertiser.business_name or "",
            "logo_url": advertiser.logo_url or "",
            "color": advertiser.widget_color or "#25D366",
            "city": advertiser.city or "",
            "loyalty": await get_card(db, advertiser, contact.id),
            "next_appointment": {
                "service": next_appt.service,
                "scheduled_at": next_appt.scheduled_at.astimezone(TZ).isoformat(),
            } if next_appt else None,
            "coupons": len(coupons),
        })
    return {"phone": phone, "businesses": out}
