"""
Twilio incoming webhook — thin transport adapter over `inbound_pipeline`.

Handles Twilio-specific concerns only: signature validation, form parsing,
media/Whisper transcription, and advertiser resolution (shared/pool number
heuristics). Everything else (bot logic) lives in
`app.services.inbound_pipeline.process_inbound_message`.
"""
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.contact import Contact
from app.models.message import Message
from app.models.user import User
from app.services.claude_service import generate_bot_response
from app.services.inbound_pipeline import InboundMessage, process_inbound_message
from app.services.twilio_service import send_whatsapp as _send_wa
from app.api.v1.chat_demo import (
    DEMO_CONTEXT,
    DEMO_BUSINESS_NAME,
    DEMO_BOT_NAME,
    DEMO_BOT_PERSONALITY,
    REDIS_TTL as DEMO_REDIS_TTL,
    MAX_HISTORY as DEMO_MAX_HISTORY,
)
from app.core.redis import get_redis_optional
from app.core.rate_limiter import limiter

logger = logging.getLogger(__name__)

SHARED_NUMBER_REDIS_PREFIX = "whatsapp_shared_chat:"


def _validate_twilio_signature(request_url: str, params: dict, signature: str) -> bool:
    """Validate X-Twilio-Signature HMAC-SHA1."""
    import base64
    sorted_params = "".join(f"{k}{v}" for k, v in sorted(params.items()))
    s = request_url + sorted_params
    mac = hmac.new(
        settings.TWILIO_AUTH_TOKEN.encode("utf-8"),
        s.encode("utf-8"),
        hashlib.sha1,
    )
    expected = base64.b64encode(mac.digest()).decode()
    return hmac.compare_digest(expected, signature)


@limiter.limit("20/minute")
async def twilio_incoming(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Handle incoming WhatsApp messages from Twilio."""
    signature = request.headers.get("X-Twilio-Signature", "")
    form_data = dict(await request.form())

    if settings.TWILIO_AUTH_TOKEN:
        url = str(request.url)
        if signature:
            if not _validate_twilio_signature(url, form_data, signature):
                import re
                alt_url = re.sub(r"^https?://[^/]+", settings.BASE_URL, url)
                if alt_url == url or not _validate_twilio_signature(alt_url, form_data, signature):
                    logger.warning("[WEBHOOK] Signature validation failed — url=%s alt_url=%s", url, alt_url)
                    if not settings.DEBUG:
                        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
        elif not settings.DEBUG:
            logger.warning("[WEBHOOK] Missing X-Twilio-Signature header — request from %s", request.client.host if request.client else "unknown")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature")

    from_number = form_data.get("From", "").replace("whatsapp:", "")
    to_number = form_data.get("To", "").replace("whatsapp:", "")
    body_text = form_data.get("Body", "").strip()
    logger.warning(
        "[WEBHOOK] INCOMING — From=%s To=%s Body=%s MessageSid=%s",
        from_number, to_number, body_text[:80], form_data.get("MessageSid", ""),
    )

    # Idempotency — skip if this message was already processed (cheap early
    # exit before advertiser resolution; process_inbound_message re-checks
    # the same twilio_sid in case of a race).
    message_sid = form_data.get("MessageSid", "")
    if message_sid:
        existing = await db.execute(
            select(Message).where(Message.twilio_sid == message_sid).limit(1)
        )
        if existing.scalar_one_or_none():
            return {"message": "ok"}

    num_media = int(form_data.get("NumMedia", "0"))
    media_url: str | None = None
    audio_transcription: str | None = None
    if num_media > 0:
        media_url = form_data.get("MediaUrl0", "")
        media_type = form_data.get("MediaContentType0", "")
        if media_url:
            is_audio = any(t in media_type for t in ("audio/", "ogg", "mpeg", "mp4", "webm", "amr"))
            if is_audio and not body_text:
                from app.services.whisper_service import transcribe_audio_url
                audio_transcription = await transcribe_audio_url(
                    media_url,
                    twilio_account_sid=settings.TWILIO_ACCOUNT_SID,
                    twilio_auth_token=settings.TWILIO_AUTH_TOKEN,
                )
                if audio_transcription:
                    body_text = audio_transcription
                else:
                    body_text = f"[audio:{media_type}]"
            elif not body_text:
                body_text = f"[media:{media_type}]{media_url}"

    # Look up advertiser: first by contact's From number (shared number support),
    # then fall back to To number lookup (dedicated/pool numbers).
    advertiser = None

    from_clean = from_number.lstrip("+").replace(" ", "")
    from_candidates = [from_number]
    if from_clean.startswith("521"):
        from_candidates.append("+52" + from_clean[3:])
    elif from_clean.startswith("52"):
        from_candidates.append("+521" + from_clean[2:])
    contact_from_result = await db.execute(
        select(Contact).where(Contact.phone.in_(from_candidates)).order_by(Contact.created_at.desc())
    )
    existing_contact = contact_from_result.scalars().first()
    if existing_contact:
        advertiser = await db.get(User, existing_contact.advertiser_id)
        logger.warning("[WEBHOOK] Step1: contact found — phone=%s advertiser=%s biz=%s", existing_contact.phone, advertiser.id if advertiser else None, advertiser.business_name if advertiser else None)
    else:
        logger.warning("[WEBHOOK] Step1: NO contact for From=%s candidates=%s", from_number, from_candidates)

    # 2. Fallback: look up advertiser by To number (dedicated/pool numbers, or shared number default)
    if not advertiser:
        to_number_clean = to_number.lstrip("+").replace(" ", "")
        candidates = [to_number, f"+{to_number_clean}", to_number_clean]
        if to_number_clean.startswith("52"):
            without1 = "+52" + to_number_clean[2:]
            with1 = "+521" + to_number_clean[2:]
            candidates.extend([without1, with1])
        logger.warning("[WEBHOOK] Step2: trying candidates=%s", candidates)
        for candidate in candidates:
            result = await db.execute(
                select(User).where(User.whatsapp_number == candidate)
            )
            advertiser = result.scalar_one_or_none()
            if advertiser:
                logger.warning("[WEBHOOK] Step2: found by whatsapp_number=%s advertiser=%s", candidate, advertiser.id)
                break
        if not advertiser:
            logger.warning("[WEBHOOK] Step2: no advertiser by To number")

    # 3. Fallback for shared Twilio number: look up most recent outbound message
    #    to this From number — the last advertiser who messaged them is the owner.
    if not advertiser and to_number in (settings.TWILIO_WHATSAPP_NUMBER, settings.TWILIO_WHATSAPP_NUMBER.replace("whatsapp:", "")):
        logger.warning("[WEBHOOK] Step3: shared number fallback — looking for outbound to From=%s", from_number)
        recent = await db.execute(
            select(Message)
            .join(Contact, Message.contact_id == Contact.id)
            .where(
                Message.direction == "outbound",
                Message.twilio_sid.isnot(None),
                Contact.phone.in_(from_candidates),
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        recent_msg = recent.scalars().first()
        if recent_msg:
            advertiser = await db.get(User, recent_msg.advertiser_id)
            logger.warning("[WEBHOOK] Step3: found outbound msg %s — advertiser=%s", recent_msg.id, advertiser.id if advertiser else None)
        else:
            logger.warning("[WEBHOOK] Step3: no outbound msgs found")

    if not advertiser:
        logger.warning("[WEBHOOK] No advertiser found for number %s", to_number)
        shared_numbers = {
            settings.TWILIO_WHATSAPP_NUMBER,
            settings.TWILIO_WHATSAPP_NUMBER.replace("whatsapp:", ""),
        }
        if to_number in shared_numbers:
            redis = await get_redis_optional()
            redis_key = f"{SHARED_NUMBER_REDIS_PREFIX}{from_number}"
            history: list[dict] = []
            if redis:
                raw = await redis.get(redis_key)
                if raw:
                    try:
                        history = json.loads(raw)
                    except json.JSONDecodeError:
                        history = []

            try:
                reply = await generate_bot_response(
                    advertiser_context=DEMO_CONTEXT,
                    conversation_history=history,
                    user_message=body_text,
                    business_name=DEMO_BUSINESS_NAME,
                    bot_name=DEMO_BOT_NAME,
                    bot_personality=DEMO_BOT_PERSONALITY,
                )
            except Exception as e:
                logger.error("[WEBHOOK] Shared-number Claude error: %s", e, exc_info=True)
                reply = (
                    "¡Hola! 👋 Bienvenido a IaRadio.\n\n"
                    "Soy el asistente virtual. ¿En qué puedo ayudarte?\n"
                    "Escríbeme y con gusto te atenderé."
                )

            if redis:
                history.append({"role": "user", "content": body_text})
                history.append({"role": "assistant", "content": reply})
                history = history[-DEMO_MAX_HISTORY:]
                await redis.setex(redis_key, DEMO_REDIS_TTL, json.dumps(history))

            await _send_wa(from_number, reply)
        else:
            try:
                fallback_reply = (
                    "¡Hola! 👋 Gracias por escribirnos.\n\n"
                    "Este número aún no está configurado para atenderte. "
                    "Si crees que es un error, por favor contacta al soporte de IaRadio."
                )
                await _send_wa(from_number, fallback_reply)
            except Exception as e:
                logger.warning("[WEBHOOK] Fallback reply failed: %s", e)
        return {"message": "advertiser_not_found"}

    async def _send(to: str, body: str) -> tuple[str | None, str | None]:
        return await _send_wa(to, body, from_number=advertiser.whatsapp_number)

    async def _send_owner(to: str, body: str) -> tuple[str | None, str | None]:
        # Intentionally no from_number — owner notifications default to the
        # shared Twilio number, same as before this file was split.
        return await _send_wa(to, body)

    inbound = InboundMessage(
        advertiser=advertiser,
        from_number=from_number,
        body_text=body_text,
        audio_transcription=audio_transcription,
        media_url=media_url,
        external_message_id=message_sid or None,
        channel="twilio",
    )
    return await process_inbound_message(db, inbound, send=_send, send_owner=_send_owner)
