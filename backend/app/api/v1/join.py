"""Registro por QR de mostrador — /api/v1/public/join/{slug}

El primer contacto sin WhatsApp de por medio: el cliente escanea el cartel
del negocio, escribe nombre y número, confirma con el código que le llega
por WhatsApp (mismo código y plantilla que /mi, customer_account.py) y
entra directo a su tarjeta. El código es lo que impide que alguien registre
el número de otro y se quede con el link de su portal (donde después
estarían sus citas y su plática).
"""
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limiter import limiter
from app.core.redis import get_redis_optional
from app.database import get_db
from app.models.contact import Contact
from app.models.user import User
from app.services.customer_account import (
    CodeError,
    canonical_phone,
    check_code,
    contact_phone_canonical,
    issue_code,
    make_account_token,
    send_code,
)
from app.services.loyalty_service import loyalty_config
from app.services.portal_service import make_portal_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/join", tags=["counter-qr"])

# Tope de códigos por negocio al día: cada uno lo cobra Meta, y el cartel es
# público — que alguien jugando con números ajenos no se coma el saldo.
BUSINESS_DAILY_CODES = 200


async def _business(db: AsyncSession, slug: str) -> User:
    user = (await db.execute(select(User).where(User.slug == slug))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")
    return user


def _clean_name(raw) -> str:
    name = " ".join(str(raw or "").split())[:100]
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Escribe tu nombre")
    return name


def _phone(raw) -> str:
    phone = canonical_phone(str(raw or ""))
    if phone is None:
        raise HTTPException(status_code=400, detail="Escribe tu número de WhatsApp a 10 dígitos")
    return phone


def _need_on(redis: AsyncRedis | None) -> AsyncRedis:
    if not settings.CUSTOMER_ACCOUNT_ENABLED:
        raise HTTPException(status_code=503, detail="Muy pronto podrás registrarte aquí.")
    if redis is None:
        raise HTTPException(status_code=503, detail="Intenta de nuevo en un momento")
    return redis


@router.get("/{slug}")
@limiter.limit("30/minute")
async def join_info(request: Request, slug: str, db: AsyncSession = Depends(get_db)) -> dict:
    user = await _business(db, slug)
    cfg = loyalty_config(user)
    return {
        "available": settings.CUSTOMER_ACCOUNT_ENABLED,
        "business": {
            "name": user.business_name or "",
            "logo_url": user.logo_url or "",
            "color": user.widget_color or "#25D366",
            "city": user.city or "",
        },
        "loyalty": {"required": cfg["stamps_required"], "reward": cfg["reward"]} if cfg else None,
    }


@router.post("/{slug}/code")
@limiter.limit("5/minute")
async def join_code(
    request: Request,
    slug: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict:
    redis = _need_on(redis)
    user = await _business(db, slug)
    _clean_name(body.get("name"))
    phone = _phone(body.get("phone"))
    day_key = f"join_codes:{user.id}:{time.strftime('%Y-%m-%d')}"
    if await redis.incr(day_key) > BUSINESS_DAILY_CODES:
        raise HTTPException(status_code=429, detail="Intenta más tarde.")
    await redis.expire(day_key, 24 * 3600)
    try:
        code = await issue_code(redis, phone)
    except CodeError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    if not await send_code(phone, code):
        raise HTTPException(status_code=503, detail="No pudimos mandarte el código. Intenta más tarde.")
    return {"message": "Te mandamos un código por WhatsApp."}


@router.post("/{slug}/verify")
@limiter.limit("10/minute")
async def join_verify(
    request: Request,
    slug: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict:
    redis = _need_on(redis)
    user = await _business(db, slug)
    name = _clean_name(body.get("name"))
    phone = _phone(body.get("phone"))
    if not await check_code(redis, phone, str(body.get("code") or "")):
        raise HTTPException(status_code=400, detail="Código incorrecto o vencido")

    contact = (
        await db.execute(
            select(Contact).where(Contact.advertiser_id == user.id, contact_phone_canonical() == phone).limit(1)
        )
    ).scalar_one_or_none()
    if contact is None:
        # Se registró solo y confirmó su número: eso es el opt-in.
        contact = Contact(advertiser_id=user.id, name=name, phone=f"+{phone}", source="qr", consent_status="confirmed")
        db.add(contact)
        await db.commit()
        await db.refresh(contact)
        from app.services.owner_alerts import alert_new_customer

        await alert_new_customer(redis, user, name, "tu QR de mostrador")
    elif contact.status == "blocked":
        raise HTTPException(status_code=403, detail="No pudimos registrarte. Pregunta en el mostrador.")
    # Si se había dado de baja de WhatsApp se queda así: usar su tarjeta en
    # la web no es pedir promociones por WhatsApp otra vez (anti-baneo).

    return {"portal_path": f"/c/{make_portal_token(contact.id)}", "account_token": make_account_token(phone)}
