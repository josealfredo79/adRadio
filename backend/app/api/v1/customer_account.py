"""Cuenta del cliente — /api/v1/public/me (ver customer_account.py).

El cliente entra con su número + un código por WhatsApp y ve todos los
negocios IaRadio donde es cliente; de ahí salta al portal de cada uno.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limiter import limiter
from app.core.redis import get_redis_optional
from app.database import get_db
from app.models.appointment import Appointment
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.message import Message
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
from app.services.loyalty_service import get_card, loyalty_config
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


def _account_phone(authorization: str) -> str:
    phone = read_account_token(authorization.removeprefix("Bearer ").strip())
    if phone is None:
        raise HTTPException(status_code=401, detail="Vuelve a entrar con tu número")
    return phone


async def _last_message(db: AsyncSession, contact_id) -> dict | None:
    """El último mensaje con ese negocio, para la lista de chats (como en
    WhatsApp): de la plática, o la última campaña que le llegó."""
    from app.api.v1.portal import _INTERNAL_MESSAGE

    rows = (await db.execute(
        select(Message, Campaign)
        .outerjoin(Campaign, Campaign.id == Message.campaign_id)
        .where(Message.contact_id == contact_id, Message.status != "queued")
        .order_by(Message.created_at.desc(), (Message.direction == "outbound").desc())
        .limit(10)
    )).all()
    for m, campaign in rows:
        if campaign is not None:
            audio = (campaign.ab_test or {}).get("campaign_mode") in ("radio", "comunitaria")
            text = f"{'🔊' if audio else '📣'} {campaign.name or 'Promoción'}"
        elif m.content and not _INTERNAL_MESSAGE.match(m.content):
            text = " ".join(m.content.split())
        else:
            continue
        return {
            "text": text[:120],
            "at": m.created_at.isoformat() if m.created_at else None,
            "from_me": m.direction == "inbound",
        }
    return None


@router.get("/businesses")
@limiter.limit("30/minute")
async def my_businesses(
    request: Request,
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> dict:
    phone = _account_phone(authorization)
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
            "agent": advertiser.bot_name or "Asistente",
            "last_message": await _last_message(db, contact.id),
        })
    # Como en WhatsApp: arriba el que tuvo actividad más reciente.
    out.sort(key=lambda b: (b["last_message"] or {}).get("at") or "", reverse=True)
    return {"phone": phone, "businesses": out}


# ─── Descubre negocios ───────────────────────────────────────────────────────
# El cliente encuentra otros negocios IaRadio y les escribe gratis, sin
# WhatsApp: al unirse queda como su cliente (con el número que ya verificó
# con el código) y se le abre el chat. Él da el paso — ningún negocio le
# escribe a quien no se unió.
DISCOVER_LIMIT = 50
# Cuentas que ya no operan: no tiene caso mandarles clientes.
INACTIVE_SUBSCRIPTIONS = ("churned", "suspended")


def _listed():
    return (
        User.directory_listed.is_(True),
        User.slug.is_not(None),
        func.coalesce(User.business_name, "") != "",
        User.subscription_status.not_in(INACTIVE_SUBSCRIPTIONS),
    )


@router.get("/discover")
@limiter.limit("30/minute")
async def discover(
    request: Request,
    q: str = "",
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> dict:
    phone = _account_phone(authorization)
    mine = await _contacts_for(db, phone)
    mine_ids = {adv.id for _, adv in mine}
    # Primero los de su ciudad (la de los negocios donde ya es cliente).
    my_cities = {(adv.city or "").strip().lower() for _, adv in mine if adv.city}

    query = select(User).where(*_listed())
    if mine_ids:
        query = query.where(User.id.not_in(mine_ids))
    term = " ".join(q.split())[:60]
    if term:
        like = f"%{term}%"
        query = query.where(or_(
            User.business_name.ilike(like), User.city.ilike(like),
            User.business_category.ilike(like), User.landing_tagline.ilike(like),
        ))
    rows = (await db.execute(query.order_by(User.business_name).limit(200))).scalars().all()
    rows = sorted(rows, key=lambda u: (u.city or "").strip().lower() not in my_cities)[:DISCOVER_LIMIT]
    out = []
    for u in rows:
        cfg = loyalty_config(u)
        out.append({
            "slug": u.slug,
            "name": u.business_name,
            "logo_url": u.logo_url or "",
            "color": u.widget_color or "#25D366",
            "city": u.city or "",
            "category": u.business_category or "",
            "tagline": u.landing_tagline or "",
            "reward": cfg["reward"] if cfg else None,
        })
    return {"businesses": out}


@router.post("/connect")
@limiter.limit("10/minute")
async def connect(
    request: Request,
    body: dict,
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict:
    """Unirse a un negocio del directorio: crea (o encuentra) su contacto ahí
    y regresa el link de su portal para abrir el chat."""
    phone = _account_phone(authorization)
    slug = str(body.get("slug") or "")
    business = (await db.execute(select(User).where(User.slug == slug, *_listed()))).scalar_one_or_none()
    if business is None:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")

    mine = await _contacts_for(db, phone)
    for contact, adv in mine:
        if adv.id == business.id:
            return {"portal_path": f"/c/{make_portal_token(contact.id)}"}
    blocked = (
        await db.execute(
            select(Contact.id).where(
                Contact.advertiser_id == business.id, contact_phone_canonical() == phone, Contact.status == "blocked"
            )
        )
    ).first()
    if blocked:
        raise HTTPException(status_code=403, detail="No pudimos unirte a este negocio.")
    # El nombre con el que ya lo conocen sus otros negocios.
    name = next((c.name for c, _ in mine if (c.name or "").strip()), "Cliente")
    contact = Contact(advertiser_id=business.id, name=name, phone=f"+{phone}", source="directory",
                      consent_status="confirmed")
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    from app.services.owner_alerts import alert_new_customer

    await alert_new_customer(redis, business, name, "el directorio de IaRadio")
    return {"portal_path": f"/c/{make_portal_token(contact.id)}"}
