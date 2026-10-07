"""Widget embebible — /api/v1/widget"""
import json
import logging
import uuid as uuid_module
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis as AsyncRedis

from app.api.idempotency import idempotent_post, store_idempotency_response
from app.core.rate_limiter import limiter
from app.core.redis import get_redis_optional

logger = logging.getLogger(__name__)
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
# Sesión ligada con "Dejar mis datos" (nombre + número que nadie verificó):
# puede pedir y agendar, pero NUNCA recibe el link de la tarjeta (/c/...) ni
# datos del cliente — si no, cualquiera escribiría el número de otro y vería
# sus citas y su plática. Las del portal (link firmado) no llevan esta marca.
UNVERIFIED_SESSION_PREFIX = "widget_unverified:"


def _strip_portal_links(reply: str) -> str:
    """Quita las líneas con link al portal (pie de confirmaciones, invitación)."""
    return "\n".join(line for line in reply.split("\n") if "/c/" not in line).rstrip()


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


ANON_SESSION_MAX_MESSAGES = 60
ANON_LIMIT_REPLY = (
    "Ahora mismo tenemos muchísimas consultas 🙏 Déjanos tus datos o escríbenos "
    "por WhatsApp y te atendemos en cuanto podamos."
)


async def _anon_chat_over_limit(redis, advertiser_id, session_id: str, *, new_session: bool) -> bool:
    """Si Redis falla o responde raro, no se bloquea a nadie (mejor dejar pasar
    a un bot que cerrarle el chat a un cliente real)."""
    try:
        return await _anon_chat_counts(redis, advertiser_id, session_id, new_session=new_session)
    except Exception:
        logger.warning("[BOT] anon chat limit check failed", exc_info=True)
        return False


async def _anon_chat_counts(redis, advertiser_id, session_id: str, *, new_session: bool) -> bool:
    import time as _time

    if new_session:
        day_key = f"webchat_anon:{advertiser_id}:{_time.strftime('%Y-%m-%d')}"
        started = int(await redis.incr(day_key))
        if started == 1:
            await redis.expire(day_key, 24 * 3600)
        if started > settings.WEB_ANON_CHATS_DAILY_MAX:
            if started == settings.WEB_ANON_CHATS_DAILY_MAX + 1:
                logger.warning("[BOT] negocio %s llegó al tope de chats anónimos del día", advertiser_id)
            return True
    sess_key = f"webchat_anon_msgs:{advertiser_id}:{session_id}"
    sent = int(await redis.incr(sess_key))
    if sent == 1:
        await redis.expire(sess_key, 24 * 3600)
    return sent > ANON_SESSION_MAX_MESSAGES


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

    contact: Contact | None = None
    if redis:
        contact_id_raw = await redis.get(f"{SESSION_CONTACT_REDIS_PREFIX}{advertiser_id}:{session_id}")
        if contact_id_raw:
            contact_id_str = contact_id_raw.decode() if isinstance(contact_id_raw, bytes) else contact_id_raw
            contact = await db.get(Contact, UUID(contact_id_str))
    unverified = bool(contact and redis and await redis.get(f"{UNVERIFIED_SESSION_PREFIX}{advertiser_id}:{session_id}"))

    if contact is None and redis:
        # Visitante anónimo: su única memoria es la sesión del navegador.
        raw = await redis.get(redis_key)
        if raw:
            try:
                history = json.loads(raw)
            except json.JSONDecodeError:
                history = []
        # Contra bots: cada mensaje llama a la IA (cuesta y gasta la cuota de
        # conversaciones del negocio). Tope de chats anónimos nuevos al día por
        # negocio y de mensajes por chat. Los clientes verificados no cuentan.
        if await _anon_chat_over_limit(redis, advertiser_id, session_id, new_session=not raw):
            return {"reply": ANON_LIMIT_REPLY, "session_id": session_id, "cards": []}

    if contact is not None:
        from app.services.web_conversation import log_turns, open_conversation

        conv = await open_conversation(db, user.id, contact.id)
        # Cliente conocido: la memoria es su plática completa (WhatsApp + web),
        # igual que en WhatsApp. Si no, el bot no sabía lo que ya contestó por
        # WhatsApp y lo repetía en la web.
        history = list(conv.messages or [])[-CHAT_MAX_HISTORY:]
        # El dueño pausó el bot para atender en persona: en la web tampoco
        # contesta el bot — el mensaje le llega al dueño al Inbox, igual que
        # en WhatsApp, y él responde desde ahí (ver web_conversation.py).
        if conv.status == "escalated":
            db.add(Message(advertiser_id=user.id, contact_id=contact.id, direction="inbound",
                           content=message, status="delivered", channel="web"))
            log_turns(conv, {"role": "user", "content": message, "channel": "web"})
            await db.commit()
            from app.services.realtime import publish_conversation_event

            await publish_conversation_event(user.id, {"type": "message", "contact_id": str(contact.id)})
            from app.services.owner_alerts import alert_web_message

            await alert_web_message(redis, user, contact.id, contact.name or "Un cliente", message)
            return {"reply": "", "handoff": True, "session_id": session_id, "cards": []}

    from app.services.appointment_booking_service import handle_appointment_booking
    from app.services.catalog_service import handle_catalog_query
    from app.services.widget_order_service import handle_widget_order

    # Catalog query is checked first — narrowest, read-only, never creates a
    # row. Appointment intent is checked before order intent — some
    # appointment keywords ("pedir cita") would otherwise also match the
    # order keyword "pedir" on its own.
    # Agente con herramientas (customer_agent.py): solo con el cliente
    # verificado (link del portal) y si el negocio lo encendió. Si no aplica
    # o falla, sigue la cadena de siempre.
    channel_reply = None
    confirm = False
    if contact is not None and not unverified:
        from app.services.customer_agent import handle as agent_handle

        agent_reply = await agent_handle(db, redis, user, contact, message, history)
        if agent_reply is not None:
            channel_reply, confirm = agent_reply.text, agent_reply.confirm
    if channel_reply is None:
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
                conversation_key=str(contact.id) if contact else f"session:{session_id}",
                redis=redis,
                contact_id=contact.id if contact and not unverified else None,
            )
        except Exception:
            logger.exception("[WIDGET-CHAT] advertiser=%s", advertiser_id)
            reply = "Gracias por tu mensaje. En breve un asesor te atenderá. 😊"

    if unverified:
        reply = _strip_portal_links(reply)
    # El bot necesita sus datos para pedir o agendar: el chat ofrece registrarse.
    from app.services.appointment_booking_service import (
        NEEDS_CONTACT_REPLY as NEEDS_CONTACT_APPT,
    )
    from app.services.widget_order_service import (
        NEEDS_CONTACT_REPLY as NEEDS_CONTACT_ORDER,
    )

    needs_contact = contact is None and reply in (NEEDS_CONTACT_APPT, NEEDS_CONTACT_ORDER)

    if contact is None and redis:
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})
        await redis.setex(redis_key, CHAT_REDIS_TTL, json.dumps(history[-CHAT_MAX_HISTORY:]))

    if contact is not None:
        # Cliente que entró desde su portal (/c/...): la plática queda en su
        # historial (el dueño la ve en el Inbox) marcada como "web" — cada
        # respuesta aquí es un mensaje de WhatsApp que no se pagó.
        # Hora explícita: con el default de la BD (inicio de la transacción) la
        # pregunta y la respuesta empataban y el chat a veces ponía la respuesta arriba.
        asked_at = datetime.now(timezone.utc)
        db.add(Message(advertiser_id=user.id, contact_id=contact.id, direction="inbound",
                       content=message, status="delivered", channel="web", created_at=asked_at))
        db.add(Message(advertiser_id=user.id, contact_id=contact.id, direction="outbound",
                       content=reply, status="delivered", channel="web",
                       created_at=asked_at + timedelta(milliseconds=1)))
        try:
            conv = await open_conversation(db, user.id, contact.id)
            log_turns(
                conv,
                {"role": "user", "content": message, "channel": "web"},
                {"role": "assistant", "content": reply, "channel": "web"},
            )
            await db.commit()
            from app.services.realtime import publish_conversation_event

            await publish_conversation_event(user.id, {"type": "message", "contact_id": str(contact.id)})
        except Exception:
            await db.rollback()
            logger.warning("[WIDGET-CHAT] Could not save web chat turn for contact=%s", contact.id, exc_info=True)

    from app.services.product_card_service import extract_product_cards, product_card
    try:
        cards = await extract_product_cards(reply, db)
        if not cards and channel_reply is None:
            # Respuesta del bot que habla de UN producto sin traer su link: su tarjeta con foto.
            from app.services.product_link_service import mentioned_product

            product = await mentioned_product(db, user.id, message, reply)
            if product:
                cards = [product_card(product)]
    except Exception:
        logger.warning("[WIDGET-CHAT] Failed to extract product cards", exc_info=True)
        cards = []

    return {"reply": reply, "session_id": session_id, "cards": cards, "needs_contact": needs_contact, "confirm": confirm}


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

    from app.core.bot_guard import is_honeypot_hit

    if is_honeypot_hit(body, request, "widget_lead"):
        return {"message": "ok", "session_id": body.get("session_id") or str(uuid_module.uuid4())}

    result = await db.execute(select(User).where(User.id == advertiser_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Widget no encontrado")

    from app.services.customer_account import canonical_phone, contact_phone_canonical

    canonical = canonical_phone(phone)
    contact_result = await db.execute(
        select(Contact).where(
            Contact.advertiser_id == advertiser_id,
            contact_phone_canonical() == canonical if canonical else Contact.phone == phone,
        ).limit(1)
    )
    contact = contact_result.scalar_one_or_none()
    is_new_contact = contact is None
    if not is_new_contact:
        # Ese número ya es cliente: sin verificar, ligar esta sesión a su
        # contacto le daría a quien lo escribió su tarjeta y su plática. Que
        # entre con su código (/q/{slug}) o desde el link que le llega por WhatsApp.
        return {
            "message": "Ese número ya está registrado con nosotros. Entra con el código que te llega por WhatsApp.",
            "existing": True,
            "session_id": body.get("session_id") or str(uuid_module.uuid4()),
        }
    if not contact:
        # Número sin verificar (cualquiera puede escribir uno ajeno, o un bot
        # inventarlo): sin consentimiento confirmado no recibe campañas en frío
        # hasta que escriba por WhatsApp (campaign_ops / inbound_pipeline).
        contact = Contact(advertiser_id=advertiser_id, name=name, phone=phone, source="widget",
                          consent_status="unconfirmed")
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
        await redis.setex(f"{UNVERIFIED_SESSION_PREFIX}{advertiser_id}:{session_id}", CHAT_REDIS_TTL, "1")

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
