"""Widget embebible — /api/v1/widget"""
import json
import logging
import uuid as uuid_module
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis as AsyncRedis

from app.api.idempotency import idempotent_post, store_idempotency_response
from app.core.redis import get_redis_optional
from app.core.rate_limiter import limiter

logger = logging.getLogger(__name__)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.schemas.contact import validate_phone_e164

router = APIRouter(prefix="/widget", tags=["widget"])

CHAT_REDIS_PREFIX = "widget_chat:"
CHAT_REDIS_TTL = 1800
CHAT_MAX_HISTORY = 20
# Links a widget session to the Contact created via POST /widget/lead, so a
# later /widget/chat call in the same session (same session_id) knows a real
# Contact already exists and can hand off to widget_order_service.
SESSION_CONTACT_REDIS_PREFIX = "widget_session_contact:"


@router.get("/snippet")
async def get_widget_snippet(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the embeddable HTML/JS snippet for this advertiser's website widget."""
    wa_number = current_user.whatsapp_number or ""
    business = (current_user.business_name or "Nosotros").replace("'", "\\'")
    bot_name = (current_user.bot_name or "Asistente").replace("'", "\\'")
    greeting = (current_user.widget_greeting or "¡Hola! ¿En qué puedo ayudarte?").replace("'", "\\'")
    color = current_user.widget_color or "#25D366"

    widget_base = (settings.WIDGET_URL or "https://www.iaradio.online").rstrip("/")
    snippet = f"""<!-- IaRadio Widget -->
<link rel="stylesheet" href="{widget_base}/widget/widget.css">
<script>
  window.IaRadioWidget = {{
    advertiserId: '{current_user.id}',
    apiBase: '{widget_base}/api/v1',
    phone: '{wa_number}',
    business: '{business}',
    agent: '{bot_name}',
    greeting: '{greeting}',
    color: '{color}',
  }};
</script>
<script src="{widget_base}/widget/widget.js" defer></script>
<!-- Fin IaRadio Widget -->"""

    return {"snippet": snippet}


@router.post("/chat/{advertiser_id}")
@limiter.limit("15/minute")
async def widget_chat(
    request: Request,
    advertiser_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict:
    """Public endpoint: a website visitor chats directly with *advertiser_id*'s
    bot, scoped to that business's own knowledge base — no WhatsApp involved
    at all. Session history is ephemeral (Redis, 30min TTL), mirroring
    /chat/demo's pattern rather than writing to Contact/Conversation/Message,
    since a widget visitor isn't a WhatsApp contact."""
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    if len(message) > 500:
        raise HTTPException(status_code=400, detail="message too long (max 500 chars)")

    result = await db.execute(select(User).where(User.id == advertiser_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Widget no encontrado")

    session_id = body.get("session_id") or str(uuid_module.uuid4())
    redis_key = f"{CHAT_REDIS_PREFIX}{advertiser_id}:{session_id}"
    history: list[dict] = []

    if redis:
        raw = await redis.get(redis_key)
        if raw:
            try:
                history = json.loads(raw)
            except json.JSONDecodeError:
                history = []

    contact: Contact | None = None
    if redis:
        contact_id_raw = await redis.get(f"{SESSION_CONTACT_REDIS_PREFIX}{advertiser_id}:{session_id}")
        if contact_id_raw:
            contact_id_str = contact_id_raw.decode() if isinstance(contact_id_raw, bytes) else contact_id_raw
            contact = await db.get(Contact, UUID(contact_id_str))

    from app.services.appointment_booking_service import handle_appointment_booking
    from app.services.catalog_service import handle_catalog_query
    from app.services.widget_order_service import handle_widget_order

    # Catalog query is checked first — narrowest, read-only, never creates a
    # row. Appointment intent is checked before order intent — some
    # appointment keywords ("pedir cita") would otherwise also match the
    # order keyword "pedir" on its own.
    channel_reply = await handle_catalog_query(db, user, message)
    if channel_reply is None:
        channel_reply = await handle_appointment_booking(db, user, contact, message, redis, channel="widget")
    if channel_reply is None:
        channel_reply = await handle_widget_order(db, user, contact, message)

    if channel_reply is not None:
        reply = channel_reply
    else:
        from app.services.rag_service import answer_with_rag

        try:
            reply = await answer_with_rag(
                advertiser_id=str(advertiser_id),
                query=message,
                conversation_history=history,
                db=db,
                business_name=user.business_name or "el negocio",
                bot_name=user.bot_name or "Asistente",
                bot_personality=user.bot_personality or "amigable y profesional",
            )
        except Exception as e:
            logger.error("[WIDGET-CHAT] advertiser=%s error=%s", advertiser_id, e, exc_info=True)
            reply = "Gracias por tu mensaje. En breve un asesor te atenderá. 😊"

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply})
    history = history[-CHAT_MAX_HISTORY:]

    if redis:
        await redis.setex(redis_key, CHAT_REDIS_TTL, json.dumps(history))

    return {"reply": reply, "session_id": session_id}


@router.post("/lead/{advertiser_id}")
@limiter.limit("10/minute")
async def widget_capture_lead(
    request: Request,
    advertiser_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict:
    """A widget visitor chooses to leave their name/phone. Materializes what
    was an ephemeral Redis-only chat into a real Contact (source='widget') +
    Conversation, so the advertiser sees it in Contacts/Inbox exactly like a
    WhatsApp lead — pulling in whatever transcript exists for *session_id*."""
    name = (body.get("name") or "").strip()
    phone_raw = (body.get("phone") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not phone_raw:
        raise HTTPException(status_code=400, detail="phone is required")
    try:
        phone = validate_phone_e164(phone_raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = await db.execute(select(User).where(User.id == advertiser_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Widget no encontrado")

    contact_result = await db.execute(
        select(Contact).where(Contact.advertiser_id == advertiser_id, Contact.phone == phone)
    )
    contact = contact_result.scalar_one_or_none()
    is_new_contact = contact is None
    if not contact:
        contact = Contact(advertiser_id=advertiser_id, name=name, phone=phone, source="widget")
        db.add(contact)
        await db.flush()

    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.advertiser_id == advertiser_id, Conversation.contact_id == contact.id
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        conv = Conversation(advertiser_id=advertiser_id, contact_id=contact.id, messages=[])
        db.add(conv)
        await db.flush()

    # A visitor can leave their data before ever sending a chat message —
    # widget.js's session_id is still null at that point. Generate one here
    # so we can hand it back and link it to this Contact regardless.
    session_id = body.get("session_id") or str(uuid_module.uuid4())

    # Pull whatever transcript exists in Redis for this session and turn it
    # into real rows — both Conversation.messages (what the Inbox thread view
    # reads) and Message rows (what the Inbox list's count/preview reads).
    if redis and body.get("session_id"):
        raw = await redis.get(f"{CHAT_REDIS_PREFIX}{advertiser_id}:{session_id}")
        if raw:
            try:
                transcript = json.loads(raw)
            except json.JSONDecodeError:
                transcript = []
            existing = list(conv.messages or [])
            conv.messages = existing + transcript
            for turn in transcript:
                direction = "inbound" if turn.get("role") == "user" else "outbound"
                db.add(Message(
                    advertiser_id=advertiser_id, contact_id=contact.id,
                    direction=direction, content=turn.get("content", ""), status="delivered",
                ))

    conv.last_activity = datetime.now(timezone.utc)
    await db.commit()

    if redis and session_id:
        await redis.setex(
            f"{SESSION_CONTACT_REDIS_PREFIX}{advertiser_id}:{session_id}", CHAT_REDIS_TTL, str(contact.id)
        )

    if is_new_contact:
        from app.services.webhook_dispatcher import dispatch_webhook_event
        await dispatch_webhook_event(
            "contact.created",
            {"id": str(contact.id), "name": contact.name, "phone": contact.phone, "source": "widget"},
            db,
            advertiser_id=advertiser_id,
        )

    return {"message": "ok", "contact_id": str(contact.id), "session_id": session_id}


@router.get("/preview/{advertiser_id}", include_in_schema=False)
@limiter.limit("10/minute")
async def widget_preview(request: Request, advertiser_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """Public endpoint to load widget config for a given advertiser (used by widget.js)."""
    result = await db.execute(select(User).where(User.id == advertiser_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404)
    return {
        "phone": user.whatsapp_number or "",
        "business": user.business_name or "",
        "agent": user.bot_name or "Asistente",
        "greeting": user.widget_greeting or "¡Hola! ¿En qué puedo ayudarte?",
        "color": user.widget_color or "#25D366",
        "position": user.widget_position or "right",
    }


@router.put("/config")
async def update_widget_config(
    request: Request,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(idempotent_post),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict:
    """Update widget customization settings for the current advertiser."""
    if "color" in body:
        color = body["color"]
        if not color.startswith("#") or len(color) not in (4, 7):
            raise HTTPException(status_code=400, detail="Color debe ser hex válido (ej. #25D366)")
        current_user.widget_color = color
    if "greeting" in body:
        if len(body["greeting"]) > 200:
            raise HTTPException(status_code=400, detail="Saludo demasiado largo (máx 200 caracteres)")
        current_user.widget_greeting = body["greeting"]
    if "position" in body:
        if body["position"] not in ("left", "right"):
            raise HTTPException(status_code=400, detail="Posición debe ser 'left' o 'right'")
        current_user.widget_position = body["position"]

    await db.commit()
    logger.info("Widget config updated for user %s", current_user.id)
    out = {"message": "Widget actualizado"}
    await store_idempotency_response(request, redis, out)
    return out


@router.get("/config")
async def get_widget_config(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the current widget configuration."""
    return {
        "color": current_user.widget_color or "#25D366",
        "greeting": current_user.widget_greeting or "¡Hola! ¿En qué puedo ayudarte?",
        "position": current_user.widget_position or "right",
    }
