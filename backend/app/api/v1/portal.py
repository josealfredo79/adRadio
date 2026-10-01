"""Portal del cliente — /api/v1/public/portal/{token}

Público (sin login): el token firmado de portal_service.py es la credencial.
Todo se filtra por el contacto del token — un cliente nunca ve citas,
pedidos ni cupones de otro, aunque sean del mismo negocio.
"""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.public_site import _first_name, _public_whatsapp_number
from app.api.v1.widget import (
    CHAT_REDIS_PREFIX,
    CHAT_REDIS_TTL,
    SESSION_CONTACT_REDIS_PREFIX,
)
from app.core.rate_limiter import limiter
from app.core.redis import get_redis_optional
from app.database import get_db
from app.models.appointment import Appointment
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.order import Order
from app.models.user import User
from app.services.availability_service import TZ
from app.services.claude_service import personalize_message
from app.services.portal_service import read_portal_token
from app.services.widget_order_service import ORDER_RESUME_WINDOW

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/portal", tags=["customer-portal"])

ACTIVE_APPOINTMENT_STATUSES = ("pending", "confirmed")
# Solo campañas comerciales — "voces" (testimonios) y recordatorios no son una
# promoción que el cliente quiera volver a ver.
PROMO_CAMPAIGN_TYPES = ("promo", "launch", "event")
PROMO_LOOKBACK = timedelta(days=30)
ORDER_STATE_LABELS = {
    "collecting_name": "En proceso",
    "collecting_address": "En proceso",
    "collecting_payment": "En proceso",
    "confirmed": "Confirmado",
    "cancelled": "Cancelado",
}


def _order_state_label(o: Order, now: datetime) -> str:
    """Un pedido a medias que ya no se retoma (ver ORDER_RESUME_WINDOW) no
    está "en proceso" — el cliente lo dejó; decirle la verdad."""
    if o.state.startswith("collecting_") and o.created_at and o.created_at <= now - ORDER_RESUME_WINDOW:
        return "Sin terminar"
    return ORDER_STATE_LABELS.get(o.state, o.state)


async def _resolve(db: AsyncSession, token: str) -> tuple[Contact, User]:
    contact_id = read_portal_token(token)
    if contact_id is None:
        raise HTTPException(status_code=404, detail="Link no válido")
    contact = await db.get(Contact, contact_id)
    if contact is None or contact.status == "blocked":
        raise HTTPException(status_code=404, detail="Link no válido")
    advertiser = await db.get(User, contact.advertiser_id)
    if advertiser is None:
        raise HTTPException(status_code=404, detail="Link no válido")
    return contact, advertiser


def _appointment_out(a: Appointment, now: datetime) -> dict:
    return {
        "id": str(a.id),
        "service": a.service,
        "scheduled_at": a.scheduled_at.astimezone(TZ).isoformat(),
        "duration_min": a.duration_min,
        "status": a.status,
        "can_cancel": a.status in ACTIVE_APPOINTMENT_STATUSES and a.scheduled_at > now,
    }


@router.get("/{token}")
@limiter.limit("30/minute")
async def get_portal(request: Request, token: str, db: AsyncSession = Depends(get_db)) -> dict:
    contact, advertiser = await _resolve(db, token)
    now = datetime.now(timezone.utc)

    appts = (
        await db.execute(
            select(Appointment)
            .where(Appointment.advertiser_id == advertiser.id, Appointment.contact_id == contact.id)
            .order_by(Appointment.scheduled_at.desc())
            .limit(20)
        )
    ).scalars().all()
    upcoming = sorted(
        (a for a in appts if a.status in ACTIVE_APPOINTMENT_STATUSES and a.scheduled_at > now),
        key=lambda a: a.scheduled_at,
    )
    upcoming_ids = {a.id for a in upcoming}
    history = [a for a in appts if a.id not in upcoming_ids][:5]

    orders = (
        await db.execute(
            select(Order)
            .where(Order.advertiser_id == advertiser.id, Order.contact_id == contact.id)
            .order_by(Order.created_at.desc())
            .limit(10)
        )
    ).scalars().all()

    coupons = (
        await db.execute(
            select(Coupon)
            .where(
                Coupon.advertiser_id == advertiser.id,
                Coupon.contact_id == contact.id,
                Coupon.expires_at > now,
                Coupon.used_count < Coupon.max_uses,
            )
            .order_by(Coupon.expires_at.asc())
        )
    ).scalars().all()

    promotions = [_promo_summary(p) for p in await _received_promos(db, contact, advertiser, now)]

    return {
        "promotions": promotions,
        "business": {
            "advertiser_id": str(advertiser.id),
            "name": advertiser.business_name or "",
            "logo_url": advertiser.logo_url or "",
            "color": advertiser.widget_color or "#25D366",
            "site_theme": advertiser.site_theme or "medianoche",
            "slug": advertiser.slug or "",
            "city": advertiser.city or "",
            "agent": advertiser.bot_name or "Asistente",
            "whatsapp_number": _public_whatsapp_number(advertiser),
        },
        "customer": {"first_name": _first_name(contact.name) or ""},
        "upcoming_appointments": [_appointment_out(a, now) for a in upcoming],
        "past_appointments": [_appointment_out(a, now) for a in history],
        "orders": [
            {
                "id": str(o.id),
                "order_number": o.order_number,
                "state": o.state,
                "state_label": _order_state_label(o, now),
                "items": o.items_raw or "",
                "payment_method": o.payment_method or "",
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ],
        "coupons": [_coupon_out(c) for c in coupons],
    }


@router.post("/{token}/appointments/{appointment_id}/cancel")
@limiter.limit("10/minute")
async def cancel_appointment(
    request: Request, token: str, appointment_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    contact, advertiser = await _resolve(db, token)
    appt = await db.get(Appointment, appointment_id)
    # Misma respuesta para "no existe" y "es de otro contacto": no revelar ids ajenos.
    if appt is None or appt.contact_id != contact.id or appt.advertiser_id != advertiser.id:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if appt.status not in ACTIVE_APPOINTMENT_STATUSES or appt.scheduled_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="Esta cita ya no se puede cancelar")

    appt.status = "cancelled"
    appt.awaiting_confirmation = False
    if appt.google_event_id and advertiser.google_refresh_token:
        try:
            from app.services.calendar_service import delete_event
            delete_event(advertiser.google_refresh_token, appt.google_event_id)
            appt.google_event_id = None
        except Exception as e:
            logger.warning("[PORTAL] Google Calendar delete failed: %s", e)
    await db.commit()

    await _notify_owner_cancelled(advertiser, appt)
    return {"message": "Cita cancelada", "appointment": _appointment_out(appt, datetime.now(timezone.utc))}


async def _notify_owner_cancelled(advertiser: User, appt: Appointment) -> None:
    """Por el número central de IaRadio si está configurado — es el único
    canal hacia el dueño que no depende de que él le haya escrito a su
    propio bot. Sin él, la cancelación se ve igual en el dashboard."""
    from app.services.owner_question_service import owner_number
    from app.services.platform_whatsapp import platform_enabled, send_platform_text

    to = owner_number(advertiser)
    if not (platform_enabled() and to):
        return
    when = appt.scheduled_at.astimezone(TZ).strftime("%d/%m %H:%M")
    try:
        await send_platform_text(
            to,
            f"❌ *Cita cancelada desde el portal*\n👤 {appt.customer_name}\n📌 {appt.service}\n🕐 {when}",
        )
    except Exception:
        logger.exception("[PORTAL] owner notify failed advertiser=%s", advertiser.id)


@router.post("/{token}/chat-session")
@limiter.limit("10/minute")
async def start_chat_session(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
    redis: AsyncRedis | None = Depends(get_redis_optional),
    body: dict | None = None,
) -> dict:
    """Abre una sesión del chat web (/widget/chat) ya ligada a este contacto,
    así el bot puede tomar pedidos y citas a su nombre sin volver a pedirle
    nombre y teléfono — y sin un solo mensaje cobrado por Meta.

    Con `promo_id` (el chat se abrió desde "¡La quiero!"), la promo y el
    cupón del cliente quedan como primer turno del historial: el bot solo
    conoce la base de conocimiento, no las campañas, y sin esto contestaba
    "¿en qué te ayudo?" a alguien que acababa de decir "la quiero"."""
    contact, advertiser = await _resolve(db, token)
    session_id = str(uuid.uuid4())
    if redis:
        await redis.setex(
            f"{SESSION_CONTACT_REDIS_PREFIX}{advertiser.id}:{session_id}", CHAT_REDIS_TTL, str(contact.id)
        )
        promo_context = await _promo_context(db, contact, advertiser, (body or {}).get("promo_id"))
        if promo_context:
            await redis.setex(
                f"{CHAT_REDIS_PREFIX}{advertiser.id}:{session_id}",
                CHAT_REDIS_TTL,
                json.dumps([{"role": "assistant", "content": promo_context}]),
            )
    return {"session_id": session_id, "advertiser_id": str(advertiser.id)}


async def _promo_context(db: AsyncSession, contact: Contact, advertiser: User, promo_id) -> str | None:
    try:
        campaign_id = uuid.UUID(str(promo_id)) if promo_id else None
    except ValueError:
        return None
    if campaign_id is None:
        return None
    promos = await _received_promos(db, contact, advertiser, datetime.now(timezone.utc), campaign_id=campaign_id)
    if not promos:
        return None
    p = promos[0]
    text = f"(Promoción vigente que le mandamos a este cliente — «{p['campaign'].name}»: {p['text']}"
    coupon = p["coupon"]
    if coupon:
        expires = coupon.expires_at.astimezone(TZ).strftime("%d/%m")
        text += f" Su cupón personal es {coupon.code} ({coupon.description or 'descuento'}), vence el {expires}."
    return text + ")"


def _banner_from_message(content: str) -> str | None:
    """El banner que se generó para ESTE contacto (cada uno lleva su nombre),
    ya sea enviado ("[BANNER] url") o esperando a que conteste
    ("[PENDING:banner] {json}")."""
    if content.startswith("[BANNER] "):
        return content[len("[BANNER] "):].strip() or None
    if content.startswith("[PENDING:banner] "):
        try:
            return json.loads(content[len("[PENDING:banner] "):]).get("banner_url")
        except (json.JSONDecodeError, AttributeError):
            return None
    return None


async def _received_promos(
    db: AsyncSession, contact: Contact, advertiser: User, now: datetime, campaign_id: uuid.UUID | None = None,
) -> list[dict]:
    """Campañas que este contacto SÍ recibió (hay un Message suyo ligado a la
    campaña) — el portal nunca muestra promos dirigidas a otro segmento."""
    q = (
        select(Campaign, Message.content)
        .join(Message, Message.campaign_id == Campaign.id)
        .where(
            Campaign.advertiser_id == advertiser.id,
            Campaign.type.in_(PROMO_CAMPAIGN_TYPES),
            Message.contact_id == contact.id,
            Message.direction == "outbound",
            Message.created_at > now - PROMO_LOOKBACK,
        )
        .order_by(Message.created_at.desc())
    )
    if campaign_id is not None:
        q = q.where(Campaign.id == campaign_id)
    rows = (await db.execute(q)).all()

    seen: dict[uuid.UUID, dict] = {}
    for campaign, content in rows:
        entry = seen.setdefault(campaign.id, {"campaign": campaign, "image_url": None})
        entry["image_url"] = entry["image_url"] or _banner_from_message(content or "")
    promos = list(seen.values())[:5]

    if promos:
        coupons = (
            await db.execute(
                select(Coupon).where(
                    Coupon.contact_id == contact.id,
                    Coupon.campaign_id.in_([p["campaign"].id for p in promos]),
                    Coupon.expires_at > now,
                    Coupon.used_count < Coupon.max_uses,
                )
            )
        ).scalars().all()
        by_campaign = {c.campaign_id: c for c in coupons}
        contact_data = {"name": contact.name, "city": contact.city}
        advertiser_data = {"business_name": advertiser.business_name, "city": advertiser.city}
        for p in promos:
            c = p["campaign"]
            p["text"] = personalize_message(c.message_text or "", contact_data, advertiser_data)
            p["image_url"] = p["image_url"] or c.image_url
            p["coupon"] = by_campaign.get(c.id)
    return promos


def _coupon_out(c: Coupon | None) -> dict | None:
    if c is None:
        return None
    return {
        "code": c.code,
        "description": c.description or "",
        "discount_type": c.discount_type,
        "discount_value": str(c.discount_value),
        "expires_at": c.expires_at.isoformat(),
    }


def _promo_summary(p: dict) -> dict:
    text = p["text"]
    return {
        "id": str(p["campaign"].id),
        "title": p["campaign"].name,
        "excerpt": text if len(text) <= 140 else text[:137].rstrip() + "…",
        "image_url": p["image_url"] or "",
        "has_coupon": p["coupon"] is not None,
    }


@router.get("/{token}/promos/{campaign_id}")
@limiter.limit("30/minute")
async def get_promo(request: Request, token: str, campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """Página completa de una promoción, personalizada para este cliente —
    es a donde lleva el link que va en el texto de la campaña."""
    contact, advertiser = await _resolve(db, token)
    promos = await _received_promos(db, contact, advertiser, datetime.now(timezone.utc), campaign_id=campaign_id)
    if not promos:
        raise HTTPException(status_code=404, detail="Promoción no disponible")
    p = promos[0]
    return {
        "id": str(p["campaign"].id),
        "title": p["campaign"].name,
        "text": p["text"],
        "image_url": p["image_url"] or "",
        "coupon": _coupon_out(p["coupon"]),
    }
