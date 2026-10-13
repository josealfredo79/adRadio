"""Coexistencia: el negocio conectó el número de su app WhatsApp Business y
lo sigue usando en su celular (docs/specs/2026-10-12-coexistencia.md).

Meta manda cuatro avisos extra para estos números:
- smb_message_echoes: lo que el dueño escribió desde su celular → se muestra
  en el Inbox ("desde tu celular") y el bot se calla 30 min con ese cliente.
- smb_app_state_sync: los contactos de su app → Contactos, sin
  consentimiento confirmado (no reciben campañas hasta que escriban).
- history: hasta 6 meses de chats → Inbox, con sus fechas reales.
- account_update: el negocio se desconectó desde su app.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.message import Message
from app.models.user import User
from app.services.web_conversation import MAX_CONV_MESSAGES, log_turns, open_conversation

logger = logging.getLogger(__name__)

OWNER_ACTIVE_TTL_SECONDS = 30 * 60
_OWNER_ACTIVE_PREFIX = "owner_phone_active:"
APP_CHANNEL = "app"  # Message.channel: lo mandó el dueño desde su app (gratis)
HISTORY_DECLINED = 2593109  # el dueño no quiso compartir el historial
_DISCONNECT_EVENTS = {"PARTNER_REMOVED", "ACCOUNT_OFFBOARDED"}


def owner_active_key(advertiser_id, contact_id) -> str:
    return f"{_OWNER_ACTIVE_PREFIX}{advertiser_id}:{contact_id}"


async def owner_is_attending(redis, advertiser_id, contact_id) -> bool:
    """¿El dueño le escribió a este cliente desde su celular hace menos de 30 min?"""
    if redis is None or contact_id is None:
        return False
    try:
        return bool(await redis.get(owner_active_key(advertiser_id, contact_id)))
    except Exception:
        logger.debug("[COEX] owner lock read failed", exc_info=True)
        return False


def phone_candidates(number: str) -> list[str]:
    """+52 / +521 (México) — mismas variantes que el pipeline de entrada."""
    digits = "".join(ch for ch in str(number or "") if ch.isdigit())
    if not digits:
        return []
    out = [f"+{digits}"]
    if digits.startswith("521"):
        out.append("+52" + digits[3:])
    elif digits.startswith("52"):
        out.append("+521" + digits[2:])
    return out


def _is_person(number: str) -> bool:
    # Grupos y listas no son números de teléfono (ej. "1203...@g.us").
    raw = str(number or "")
    return bool(raw) and "@" not in raw and raw.lstrip("+").isdigit()


def _text_of(msg: dict) -> str:
    kind = msg.get("type", "")
    if kind == "text":
        return (msg.get("text") or {}).get("body", "").strip()
    if kind in ("image", "video", "document", "audio", "sticker", "media_placeholder"):
        caption = (msg.get(kind) or {}).get("caption", "") if isinstance(msg.get(kind), dict) else ""
        return f"📎 archivo{': ' + caption if caption else ''}"
    return f"({kind})" if kind else ""


def _when(ts) -> datetime:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


async def advertiser_for(db: AsyncSession, phone_number_id: str | None, waba_id: str | None = None) -> User | None:
    if phone_number_id:
        user = (await db.execute(select(User).where(User.meta_phone_number_id == str(phone_number_id)))).scalars().first()
        if user:
            return user
    if waba_id:
        return (await db.execute(select(User).where(User.meta_waba_id == str(waba_id)))).scalars().first()
    return None


async def _contact(db: AsyncSession, advertiser_id: uuid.UUID, number: str, name: str | None = None,
                   create: bool = True) -> Contact | None:
    candidates = phone_candidates(number)
    if not candidates:
        return None
    found = (await db.execute(
        select(Contact).where(Contact.advertiser_id == advertiser_id, Contact.phone.in_(candidates)).limit(1)
    )).scalar_one_or_none()
    if found or not create:
        return found
    contact = Contact(advertiser_id=advertiser_id, name=(name or candidates[0])[:255], phone=candidates[0],
                      source="whatsapp_app", consent_status="unconfirmed")
    db.add(contact)
    await db.flush()
    return contact


async def _known_ids(db: AsyncSession, ids: list[str]) -> set[str]:
    ids = [i for i in ids if i]
    if not ids:
        return set()
    rows = (await db.execute(select(Message.wa_message_id).where(Message.wa_message_id.in_(ids)))).scalars().all()
    return set(rows)


async def handle_echoes(db: AsyncSession, redis, advertiser: User, value: dict) -> int:
    """Lo que el dueño mandó desde su celular. Regresa cuántos se guardaron."""
    echoes = value.get("message_echoes") or []
    known = await _known_ids(db, [e.get("id", "") for e in echoes])
    saved = 0
    touched: set[uuid.UUID] = set()
    for echo in echoes:
        if not _is_person(echo.get("to")) or echo.get("id") in known:
            continue
        text = _text_of(echo)
        if not text:
            continue
        contact = await _contact(db, advertiser.id, echo["to"])
        at = _when(echo.get("timestamp"))
        db.add(Message(advertiser_id=advertiser.id, contact_id=contact.id, direction="outbound", content=text,
                       status="sent", sender="owner", channel=APP_CHANNEL, wa_message_id=echo.get("id"),
                       created_at=at, sent_at=at))
        conv = await open_conversation(db, advertiser.id, contact.id)
        log_turns(conv, {"role": "assistant", "content": text, "sender": "owner", "channel": APP_CHANNEL})
        touched.add(contact.id)
        saved += 1
    await db.commit()
    if redis is not None:
        for contact_id in touched:
            try:
                await redis.setex(owner_active_key(advertiser.id, contact_id), OWNER_ACTIVE_TTL_SECONDS, "1")
            except Exception:
                logger.warning("[COEX] owner lock write failed", exc_info=True)
    if touched:
        from app.services.realtime import publish_conversation_event

        for contact_id in touched:
            await publish_conversation_event(advertiser.id, {"type": "message", "contact_id": str(contact_id)})
    return saved


async def handle_contacts(db: AsyncSession, advertiser: User, value: dict) -> int:
    """Contactos de la app → Contactos. Los que ya existían no se tocan;
    "remove" no borra nada (pueden ser clientes del bot)."""
    added = 0
    for item in value.get("state_sync") or []:
        if item.get("type") != "contact" or item.get("action") != "add":
            continue
        info = item.get("contact") or {}
        number = info.get("phone_number")
        if not _is_person(number):
            continue
        before = await _contact(db, advertiser.id, number, create=False)
        if before is None:
            await _contact(db, advertiser.id, number, name=info.get("full_name") or info.get("first_name"))
            added += 1
    await db.commit()
    return added


async def handle_history(db: AsyncSession, advertiser: User, value: dict) -> int:
    """Chats viejos → Inbox con sus fechas reales, sin duplicar."""
    imported = 0
    for chunk in value.get("history") or []:
        errors = chunk.get("errors") or []
        if any(e.get("code") == HISTORY_DECLINED for e in errors):
            logger.info("[COEX] advertiser=%s no compartió su historial", advertiser.id)
            continue
        for thread in chunk.get("threads") or []:
            customer = thread.get("id")
            if not _is_person(customer):
                continue
            messages = sorted(thread.get("messages") or [], key=lambda m: int(m.get("timestamp") or 0))
            known = await _known_ids(db, [m.get("id", "") for m in messages])
            contact = await _contact(db, advertiser.id, customer)
            customer_numbers = {c.lstrip("+") for c in phone_candidates(customer)}
            turns = []
            for m in messages:
                text = _text_of(m)
                if not text or m.get("id") in known:
                    continue
                # Lo escribió el cliente si viene de su número; si no, el dueño.
                inbound = "".join(ch for ch in str(m.get("from") or "") if ch.isdigit()) in customer_numbers
                at = _when(m.get("timestamp"))
                db.add(Message(advertiser_id=advertiser.id, contact_id=contact.id,
                               direction="inbound" if inbound else "outbound", content=text,
                               status="delivered" if inbound else "sent",
                               sender=None if inbound else "owner", channel=None if inbound else APP_CHANNEL,
                               wa_message_id=m.get("id"), created_at=at))
                turns.append({"role": "user", "content": text} if inbound
                             else {"role": "assistant", "content": text, "sender": "owner", "channel": APP_CHANNEL})
                imported += 1
            if turns:
                conv = await open_conversation(db, advertiser.id, contact.id)
                # Lo viejo va ANTES de lo que ya hubiera en la plática.
                conv.messages = (turns + list(conv.messages or []))[-MAX_CONV_MESSAGES:]
        await db.commit()
    return imported


async def handle_account_update(db: AsyncSession, advertiser: User, value: dict) -> bool:
    """El negocio se desconectó desde su app: el bot deja de enviar por ahí."""
    if value.get("event") not in _DISCONNECT_EVENTS:
        return False
    advertiser.meta_connection_status = "not_connected"
    advertiser.meta_coexistence = False
    await db.commit()
    logger.warning("[COEX] advertiser=%s se desconectó (%s)", advertiser.id, value.get("event"))
    return True


async def request_initial_sync(phone_number_id: str, token: str) -> dict[str, str]:
    """Pide a Meta los contactos y el historial (una sola vez, dentro de 24 h).
    Regresa {sync_type: request_id | "error: …"}; nunca lanza."""
    import httpx

    from app.config import settings

    url = f"{settings.META_GRAPH_BASE_URL}/{settings.META_GRAPH_API_VERSION}/{phone_number_id}/smb_app_data"
    out: dict[str, str] = {}
    for sync_type in ("smb_app_state_sync", "history"):
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, headers={"Authorization": f"Bearer {token}"},
                                         json={"messaging_product": "whatsapp", "sync_type": sync_type})
            data = resp.json() if resp.content else {}
            if resp.is_error:
                out[sync_type] = f"error: {(data.get('error') or {}).get('message', resp.status_code)}"
            else:
                out[sync_type] = str(data.get("request_id", "ok"))
        except Exception as e:  # la conexión ya quedó; esto solo se registra
            out[sync_type] = f"error: {e}"
    logger.info("[COEX] sync solicitado phone=%s → %s", phone_number_id, out)
    return out


async def is_on_business_app(phone_number_id: str, token: str) -> bool | None:
    """¿El número también está en la app WhatsApp Business (coexistencia)?
    Meta lo dice con `is_on_biz_app`. None si no se pudo saber. Sirve de red
    por si el navegador no recibió el aviso FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING:
    registrar un número de coexistencia lo prohíbe Meta."""
    import httpx

    from app.config import settings

    url = f"{settings.META_GRAPH_BASE_URL}/{settings.META_GRAPH_API_VERSION}/{phone_number_id}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"},
                                    params={"fields": "is_on_biz_app,platform_type"})
        if resp.is_error:
            return None
        value = resp.json().get("is_on_biz_app")
        return value if isinstance(value, bool) else None
    except Exception:
        logger.warning("[COEX] is_on_biz_app check failed phone=%s", phone_number_id, exc_info=True)
        return None
