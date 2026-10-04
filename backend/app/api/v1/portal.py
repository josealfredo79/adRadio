"""Portal del cliente — /api/v1/public/portal/{token}

Público (sin login): el token firmado de portal_service.py es la credencial.
Todo se filtra por el contacto del token — un cliente nunca ve citas,
pedidos ni cupones de otro, aunque sean del mismo negocio.
"""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import JSONResponse
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.public_site import _first_name, _public_whatsapp_number
from app.api.v1.widget import (
    CHAT_REDIS_PREFIX,
    CHAT_REDIS_TTL,
    SESSION_CONTACT_REDIS_PREFIX,
)
from app.config import settings
from app.core.rate_limiter import limiter
from app.core.redis import get_redis_optional
from app.database import get_db
from app.models.appointment import Appointment
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.order import Order
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services.availability_service import TZ
from app.services.claude_service import personalize_message
from app.services.loyalty_service import add_stamp, get_card
from app.services.portal_service import read_portal_token
from app.services.web_push import push_enabled
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

    # Regalo de bienvenida: el primer sello cae al abrir la tarjeta.
    if await add_stamp(db, advertiser, contact.id, "welcome"):
        await db.commit()
    loyalty = await get_card(db, advertiser, contact.id)

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

    push_count = (
        await db.execute(select(PushSubscription.id).where(PushSubscription.contact_id == contact.id))
    ).scalars().all()

    return {
        "push": {
            "available": push_enabled(),
            "public_key": settings.VAPID_PUBLIC_KEY if push_enabled() else "",
            "subscribed_devices": len(push_count),
        },
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
        "loyalty": loyalty,
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



@router.post("/{token}/appointments/{appointment_id}/confirm")
@limiter.limit("10/minute")
async def confirm_appointment(
    request: Request, token: str, appointment_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    """El "Responde 1 para confirmar" del recordatorio de WhatsApp, pero desde
    el portal — es a donde lleva la notificación web del recordatorio."""
    contact, advertiser = await _resolve(db, token)
    appt = await db.get(Appointment, appointment_id)
    if appt is None or appt.contact_id != contact.id or appt.advertiser_id != advertiser.id:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    if appt.status not in ACTIVE_APPOINTMENT_STATUSES or appt.scheduled_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="Esta cita ya no se puede confirmar")
    appt.status = "confirmed"
    appt.awaiting_confirmation = False
    await db.commit()
    return {"message": "Cita confirmada", "appointment": _appointment_out(appt, datetime.now(timezone.utc))}


def _valid_subscription(body: dict) -> tuple[str, str, str]:
    endpoint = str(body.get("endpoint") or "")
    keys = body.get("keys") or {}
    p256dh, auth = str(keys.get("p256dh") or ""), str(keys.get("auth") or "")
    # Solo https: el servidor le hace POST a este endpoint, no debe poder
    # apuntar a cualquier cosa (ej. un host interno).
    if not endpoint.startswith("https://") or len(endpoint) > 1000:
        raise HTTPException(status_code=400, detail="Suscripción no válida")
    if not (0 < len(p256dh) <= 255 and 0 < len(auth) <= 255):
        raise HTTPException(status_code=400, detail="Suscripción no válida")
    return endpoint, p256dh, auth


@router.post("/{token}/push/subscribe")
@limiter.limit("10/minute")
async def push_subscribe(request: Request, token: str, body: dict, db: AsyncSession = Depends(get_db)) -> dict:
    if not push_enabled():
        raise HTTPException(status_code=404, detail="Notificaciones no disponibles")
    contact, advertiser = await _resolve(db, token)
    endpoint, p256dh, auth = _valid_subscription(body)

    sub = (await db.execute(select(PushSubscription).where(PushSubscription.endpoint == endpoint))).scalar_one_or_none()
    if sub is None:
        sub = PushSubscription(endpoint=endpoint, advertiser_id=advertiser.id, contact_id=contact.id, p256dh=p256dh, auth=auth)
        db.add(sub)
    else:
        # Mismo navegador, otro link (ej. celular compartido): el último que
        # activó los avisos es el dueño de este navegador.
        sub.advertiser_id, sub.contact_id = advertiser.id, contact.id
        sub.p256dh, sub.auth = p256dh, auth
        sub.failure_count = 0
    sub.user_agent = (request.headers.get("user-agent") or "")[:300] or None
    # El otro sello de regalo: los avisos web son lo que luego ahorra WhatsApp.
    stamped = await add_stamp(db, advertiser, contact.id, "push")
    await db.commit()
    return {"message": "Notificaciones activadas", "stamped": stamped}


@router.post("/{token}/push/unsubscribe")
@limiter.limit("10/minute")
async def push_unsubscribe(request: Request, token: str, body: dict, db: AsyncSession = Depends(get_db)) -> dict:
    contact, _advertiser = await _resolve(db, token)
    endpoint = str(body.get("endpoint") or "")
    await db.execute(
        delete(PushSubscription).where(PushSubscription.endpoint == endpoint, PushSubscription.contact_id == contact.id)
    )
    await db.commit()
    return {"message": "Notificaciones desactivadas"}


@router.post("/{token}/opened")
@limiter.limit("30/minute")
async def notification_opened(request: Request, token: str, body: dict, db: AsyncSession = Depends(get_db)) -> dict:
    """El cliente tocó una notificación web — el equivalente al "leído" de
    WhatsApp, para que las estadísticas de la campaña lo cuenten."""
    contact, _advertiser = await _resolve(db, token)
    try:
        message_id = uuid.UUID(str(body.get("message_id")))
    except ValueError:
        return {"ok": False}
    msg = await db.get(Message, message_id)
    if msg is None or msg.contact_id != contact.id or not (msg.content or "").startswith("[PUSH]"):
        return {"ok": False}
    if msg.status != "read":
        msg.status = "read"
        msg.read_at = datetime.now(timezone.utc)
        await db.commit()
    return {"ok": True}


@router.get("/{token}/manifest.webmanifest")
@limiter.limit("30/minute")
async def portal_manifest(request: Request, token: str, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Manifest por cliente: "Agregar a inicio" instala el portal como la app
    del negocio (su nombre, su color) y abre directo en /c/{token}. En
    iPhone es requisito para recibir notificaciones web."""
    _contact, advertiser = await _resolve(db, token)
    name = advertiser.business_name or "Mi negocio"
    color = advertiser.widget_color or "#25D366"
    icons = [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
    ]
    if advertiser.logo_url:
        icons.insert(0, {"src": advertiser.logo_url, "sizes": "any"})
    return JSONResponse(
        {
            "name": name,
            "short_name": name[:12],
            "start_url": f"/c/{token}",
            "scope": "/c/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": color,
            "lang": "es-MX",
            "icons": icons,
        },
        media_type="application/manifest+json",
    )


# ─── Platicar con voz en el chat del portal ──────────────────────────────────
# Para que la web sea más cómoda que WhatsApp: el cliente habla en vez de
# escribir y el bot le contesta en voz alta. El link del portal es la
# credencial (igual que el resto de este archivo) y hay límites por minuto.
PORTAL_AUDIO_MAX_BYTES = 2 * 1024 * 1024  # ~1 minuto de voz comprimida
PORTAL_SPEAK_MAX_CHARS = 600


@router.post("/{token}/listen")
@limiter.limit("10/minute")
async def portal_listen(
    request: Request,
    token: str,
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Audio del cliente → texto (Whisper). El texto luego va por el mismo
    chat (/widget/chat) que si lo hubiera escrito."""
    from app.api.v1.voice_setup import read_transcript

    await _resolve(db, token)
    transcript = await read_transcript(audio, text, PORTAL_AUDIO_MAX_BYTES, 500, "1 minuto")
    return {"transcript": transcript[:500]}


@router.post("/{token}/speak")
@limiter.limit("20/minute")
async def portal_speak(request: Request, token: str, body: dict, db: AsyncSession = Depends(get_db)) -> Response:
    """La respuesta del bot dicha en voz alta (edge-tts, voz mexicana, sin
    costo). Si falla, el navegador usa su propia voz."""
    from app.services.radio.tts import _tts_edge

    await _resolve(db, token)
    text = " ".join(str(body.get("text") or "").replace("*", "").split())[:PORTAL_SPEAK_MAX_CHARS]
    if not text:
        raise HTTPException(status_code=400, detail="Nada que decir")
    try:
        audio = await _tts_edge(text, "es-MX-DaliaNeural", rate="+0%", pitch="+0Hz")
    except Exception:
        logger.warning("[PORTAL] TTS failed", exc_info=True)
        raise HTTPException(status_code=503, detail="Voz no disponible")
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})

