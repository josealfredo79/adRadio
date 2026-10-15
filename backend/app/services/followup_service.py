"""Seguimiento automático de interesados (spec docs/specs/2026-10-15-seguimiento-automatico.md).

Quien preguntó (plática tibia o caliente) y no agendó, pidió ni canjeó recibe
UN mensaje ~20 h después de su último mensaje, sobre lo que preguntó:
- por la web (aviso push + burbuja en su chat), gratis, si activó los avisos;
- si no, por WhatsApp solo si su ventana de 24 h sigue abierta (texto normal,
  sin plantilla ni costo de marketing);
- si no hay canal gratis, no se le escribe: va en el resumen de las 8 am del
  dueño ("preguntaron y no compraron").
Uno por cliente por semana (contacts.last_followup_at), nunca de 9 pm a 9 am,
y el dueño lo apaga en Configuración (users.followup_enabled).
"""
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.order import Order
from app.models.user import User
from app.services.availability_service import TZ

logger = logging.getLogger(__name__)

FOLLOWUP_AFTER = timedelta(hours=20)
# Margen antes de que cierren las 24 h de WhatsApp (la tarea corre cada 15 min).
WHATSAPP_LIMIT = timedelta(hours=23, minutes=30)
# Por la web se puede mandar más tarde (p. ej. a las 9 am tras la noche).
WEB_LIMIT = timedelta(hours=72)
ONCE_PER = timedelta(days=7)
# Cuánto antes de su último mensaje empezó "esta" plática para ver si ya compró.
EPISODE = timedelta(hours=48)
DAY_START, DAY_END = 9, 21
PENDING_FOLLOWUP = "owner_pending_followup:"
PENDING_TTL = 2 * 24 * 3600
FALLBACK = "¡Hola, {name}! ¿Pudiste resolver lo que buscabas? Aquí estoy para ayudarte 🙂"


def is_daytime(now: datetime) -> bool:
    return DAY_START <= now.astimezone(TZ).hour < DAY_END


_TITLES = {"don", "doña", "dona", "sr", "sra", "srta", "lic", "ing", "dr", "dra", "profe", "prof", "mtro", "mtra"}


def _first_name(contact: Contact) -> str:
    """"Don Raúl" → "Raúl" (con la IA real salía "Hola Don"); un teléfono no es nombre."""
    words = [w for w in (contact.name or "").split() if w.lower().rstrip(".") not in _TITLES]
    raw = words[0] if words else ""
    return "" if (raw.startswith("+") or raw.isdigit()) else raw


async def _last_inbound(db: AsyncSession, contact_id) -> Message | None:
    return (await db.execute(
        select(Message).where(Message.contact_id == contact_id, Message.direction == "inbound")
        .order_by(Message.created_at.desc()).limit(1)
    )).scalar_one_or_none()


async def _converted(db: AsyncSession, advertiser_id, contact_id, since: datetime, now: datetime) -> bool:
    """¿Ya agendó, pidió o canjeó en esta plática (o tiene una cita por venir)?"""
    checks = (
        select(Appointment.id).where(
            Appointment.advertiser_id == advertiser_id, Appointment.contact_id == contact_id,
            or_(Appointment.created_at >= since,
                (Appointment.scheduled_at > now) & Appointment.status.in_(("pending", "confirmed"))),
        ),
        select(Order.id).where(Order.advertiser_id == advertiser_id, Order.contact_id == contact_id,
                               Order.created_at >= since),
        select(Coupon.id).where(Coupon.advertiser_id == advertiser_id, Coupon.contact_id == contact_id,
                                Coupon.redeemed_at >= since),
    )
    for q in checks:
        if (await db.execute(q.limit(1))).first() is not None:
            return True
    return False


async def write_message(advertiser: User, contact: Contact, conv: Conversation) -> str:
    """Un mensaje corto sobre lo que preguntó, con la cadena barata de IA. Si
    falla o sale raro, el mensaje fijo (caso 11)."""
    from app.services.llm_client import chat_completion

    name = _first_name(contact)
    fallback = FALLBACK.format(name=name) if name else FALLBACK.replace(", {name}", "")
    turns = [t for t in (conv.messages or []) if t.get("role") in ("user", "assistant")][-8:]
    if not turns:
        return fallback
    transcript = "\n".join(
        f"{'Cliente' if t['role'] == 'user' else 'Negocio'}: {str(t.get('content') or '')[:300]}" for t in turns
    )
    system = (
        f"Eres el asistente de {advertiser.business_name or 'el negocio'}. El cliente{f' {name}' if name else ''} "
        "preguntó algo ayer y no compró ni agendó. Escribe UN mensaje de seguimiento: máximo 2 frases, que "
        "mencione lo que preguntó y le ofrezca ayudarle a concretarlo (apartarlo, pedirlo o agendar). "
        "No inventes precios, descuentos, existencias ni horarios que no estén en la plática. "
        "Español de México, cálido, máximo 1 emoji. Responde solo con el mensaje."
    )
    try:
        text = await chat_completion([{"role": "user", "content": f"La plática:\n{transcript}"}],
                                     system=system, max_tokens=150, temperature=0.5)
    except Exception:
        logger.warning("[FOLLOWUP] AI failed advertiser=%s — fixed message", advertiser.id, exc_info=True)
        return fallback
    text = re.sub(r"^\s*(mensaje|negocio)\s*:\s*", "", (text or "").strip(), flags=re.IGNORECASE).strip().strip('"')
    if not text or len(text) > 400 or "{" in text:
        return fallback
    return text


async def _send_web(db: AsyncSession, advertiser: User, contact: Contact, text: str) -> bool:
    from app.services.portal_service import portal_url
    from app.services.web_push import push_to_contact

    try:
        accepted = await push_to_contact(
            db, contact.id, title=advertiser.business_name or "Tu negocio", body=text,
            url=f"{portal_url(contact.id)}?chat=1", tag=f"followup-{contact.id}",
        )
    except Exception:
        logger.warning("[FOLLOWUP] push failed contact=%s", contact.id, exc_info=True)
        return False
    return accepted > 0


async def run_followups(db: AsyncSession, redis, now: datetime | None = None) -> dict[str, int]:
    """Celery beat cada 15 min. Regresa cuántos se mandaron por web, por
    WhatsApp y cuántos se le listaron al dueño."""
    from app.services.meta_service import send_whatsapp
    from app.services.trial_lifecycle import is_paused
    from app.services.web_conversation import log_turns
    from app.services.web_push import contacts_with_push

    now = now or datetime.now(timezone.utc)
    counts = {"web": 0, "whatsapp": 0, "owner": 0}
    if not is_daytime(now):
        return counts

    rows = (await db.execute(
        select(Conversation, User, Contact)
        .join(User, User.id == Conversation.advertiser_id)
        .join(Contact, Contact.id == Conversation.contact_id)
        .where(
            Conversation.status == "active",
            Conversation.lead_score.in_(("warm", "hot")),
            Conversation.last_activity <= now - FOLLOWUP_AFTER,
            Conversation.last_activity >= now - WEB_LIMIT - timedelta(hours=1),
            User.followup_enabled.is_(True),
            Contact.status == "active",
            or_(Contact.last_followup_at.is_(None), Contact.last_followup_at < now - ONCE_PER),
        )
    )).all()

    for conv, advertiser, contact in rows:
        if is_paused(advertiser, now):
            continue
        last = await _last_inbound(db, contact.id)
        if last is None:
            continue
        age = now - last.created_at
        if age < FOLLOWUP_AFTER or age > WEB_LIMIT:
            continue
        if await _converted(db, advertiser.id, contact.id, last.created_at - EPISODE, now):
            continue

        has_push = contact.id in await contacts_with_push(db, [contact.id])
        whatsapp_open = last.channel != "web" and age < WHATSAPP_LIMIT and bool(contact.phone)
        channel = None
        text = None
        wamid = None
        if has_push or whatsapp_open:
            text = await write_message(advertiser, contact, conv)
            if has_push and await _send_web(db, advertiser, contact, text):
                channel = "web"
            elif whatsapp_open:
                wamid, err = await send_whatsapp(contact.phone, text, advertiser=advertiser)
                if wamid:
                    channel = "whatsapp"
                else:
                    logger.warning("[FOLLOWUP] whatsapp not sent contact=%s: %s", contact.id, err)

        if channel:
            turn = {"role": "assistant", "content": text}
            if channel == "web":
                turn["channel"] = "web"
            log_turns(conv, turn)
            db.add(Message(
                advertiser_id=advertiser.id, contact_id=contact.id, direction="outbound", content=text,
                status="sent", sent_at=now, channel="web" if channel == "web" else None, wa_message_id=wamid,
            ))
            counts[channel] += 1
        elif redis is not None:
            # Caso 4: sin canal gratis, lo ve el dueño en su resumen de las 8 am.
            key = f"{PENDING_FOLLOWUP}{advertiser.id}"
            await redis.sadd(key, contact.name or contact.phone or "Un cliente")
            await redis.expire(key, PENDING_TTL)
            counts["owner"] += 1
        else:
            continue  # sin Redis no hay dónde anotarlo: se reintenta en la siguiente vuelta
        contact.last_followup_at = now
        await db.commit()
        logger.info("[FOLLOWUP] advertiser=%s contact=%s channel=%s", advertiser.id, contact.id, channel or "owner")
    return counts
