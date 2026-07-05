"""
Twilio incoming webhook — handle inbound WhatsApp messages.
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from sqlalchemy.exc import IntegrityError
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.order import Order
from app.models.appointment import Appointment
from app.models.customer_story import CustomerStory
from app.models.user import User
from app.services.coupon_service import is_redeem_intent, is_expired
from app.services.rag_service import answer_with_rag
from app.services.claude_service import detect_order_intent, detect_plan_purchase_intent, generate_bot_response, personalize_message
from app.services.template_lookup import get_template
from app.services.twilio_service import send_whatsapp as _send_wa
from app.api.v1.webhooks_pkg.lead_score import calculate_lead_score
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

    # Idempotency — skip if this message was already processed
    message_sid = form_data.get("MessageSid", "")
    if message_sid:
        existing = await db.execute(
            select(Message).where(Message.twilio_sid == message_sid).limit(1)
        )
        if existing.scalar_one_or_none():
            return {"message": "ok"}

    num_media = int(form_data.get("NumMedia", "0"))
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

    # 1. Try to find existing contact by their phone → get their advertiser
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

    stop_words = {"baja", "stop", "no quiero", "cancelar", "salir"}
    if body_text.lower() in stop_words:
        contact_result = await db.execute(
            select(Contact).where(
                Contact.advertiser_id == advertiser.id,
                Contact.phone == from_number,
            )
        )
        contact = contact_result.scalar_one_or_none()
        if contact:
            contact.status = "unsubscribed"
            contact.engagement_score = 0
            await db.commit()
        return {"message": "ok"}

    # Appointment reschedule handler
    if advertiser:
        reschedule_result = await db.execute(
            select(Appointment).where(
                Appointment.advertiser_id == advertiser.id,
                Appointment.awaiting_reschedule == True,
                Appointment.status == "cancelled",
            ).order_by(Appointment.scheduled_at.desc())
        )
        reschedule_appt = reschedule_result.scalars().first()
        if reschedule_appt:
            normalized = body_text.strip().lower()
            if normalized in ("1", "si", "sí", "s", "yes", "y", "claro", "por supuesto", "reagendar"):
                reschedule_appt.awaiting_reschedule = False
                await db.commit()
                _tpl = await get_template(db, str(advertiser.id), "Cita", "appt_reschedule_yes")
                reply = personalize_message(_tpl, {"name": "", "city": ""}, {"business_name": advertiser.business_name or "", "city": ""}) if _tpl else (
                    "¡Genial! 📅\n"
                    "Por favor escríbeme qué día y hora prefieres esta semana "
                    "y revisaré la disponibilidad para agendarte."
                )
                await _send_wa(from_number, reply, from_number=advertiser.whatsapp_number)
                return {"message": "ok"}
            elif normalized in ("2", "no", "n", "nop", "cancelar"):
                reschedule_appt.awaiting_reschedule = False
                await db.commit()
                _tpl = await get_template(db, str(advertiser.id), "Cita", "appt_reschedule_no")
                reply = personalize_message(_tpl, {"name": "", "city": ""}, {"business_name": "", "city": ""}) if _tpl else "Entendido 👍. ¡Escríbenos cuando estés listo/a!"
                await _send_wa(from_number, reply, from_number=advertiser.whatsapp_number)
                return {"message": "ok"}

    # Appointment confirmation handler
    _appt_reply: str | None = None
    confirm_keywords = {"1", "si", "sí", "yes", "confirmo", "confirmar", "✅", "ok", "dale"}
    cancel_keywords  = {"2", "no", "cancela", "cancelar", "cancelar cita", "no puedo", "❌"}
    normalized = body_text.lower().strip()

    if normalized in confirm_keywords or normalized in cancel_keywords:
        appt_result = await db.execute(
            select(Appointment).where(
                Appointment.advertiser_id == advertiser.id,
                Appointment.awaiting_confirmation == True,
                Appointment.status.in_(["pending", "confirmed"]),
            ).order_by(Appointment.scheduled_at.asc())
        )
        pending_appt = appt_result.scalars().first()

        if pending_appt:
            from datetime import datetime
            hora = pending_appt.scheduled_at.strftime("%I:%M %p").lstrip("0")
            fecha = pending_appt.scheduled_at.strftime("%A %d de %B")
            biz_name = advertiser.business_name or "el negocio"
            from_wa = advertiser.whatsapp_number

            if normalized in confirm_keywords:
                pending_appt.status = "confirmed"
                pending_appt.awaiting_confirmation = False
                _tpl = await get_template(db, str(advertiser.id), "Cita", "appt_confirm")
                _ac = {
                    "nombre": pending_appt.customer_name or "Cliente",
                    "primer_nombre": (pending_appt.customer_name or "Cliente").split()[0],
                    "servicio": pending_appt.service or "",
                    "fecha": fecha,
                    "hora": hora,
                    "city": "",
                }
                _appt_reply = personalize_message(_tpl, _ac, {"business_name": biz_name, "city": ""}) if _tpl else (
                    f"✅ *¡Cita confirmada!*\n\n"
                    f"📌 {pending_appt.service}\n"
                    f"🕐 {fecha} a las {hora}\n"
                    f"🏪 {biz_name}\n\n"
                    f"¡Te esperamos! Si necesitas reagendar escríbenos 😊"
                )
                owner_notify = (
                    f"✅ *Cita confirmada por el cliente*\n"
                    f"👤 {pending_appt.customer_name} ({from_number})\n"
                    f"📌 {pending_appt.service}\n"
                    f"🕐 {fecha} a las {hora}"
                )
            else:
                pending_appt.status = "cancelled"
                pending_appt.awaiting_confirmation = False
                pending_appt.awaiting_reschedule = True
                _tpl = await get_template(db, str(advertiser.id), "Cita", "appt_cancel")
                _acl = {
                    "nombre": pending_appt.customer_name or "Cliente",
                    "primer_nombre": (pending_appt.customer_name or "Cliente").split()[0],
                    "servicio": pending_appt.service or "",
                    "fecha": fecha,
                    "hora": hora,
                    "city": "",
                }
                _appt_reply = personalize_message(_tpl, _acl, {"business_name": biz_name, "city": ""}) if _tpl else (
                    f"❌ Cita cancelada.\n\n"
                    f"Sin problema, {pending_appt.customer_name.split()[0]}.\n"
                    f"¿Te gustaría que te muestre los horarios disponibles para reagendar tu cita? Responde *SÍ* o *NO* 📅"
                )
                owner_notify = (
                    f"❌ *Cita CANCELADA por el cliente*\n"
                    f"👤 {pending_appt.customer_name} ({from_number})\n"
                    f"📌 {pending_appt.service}\n"
                    f"🕐 {fecha} a las {hora}"
                )

            await db.commit()
            await _send_wa(from_number, _appt_reply, from_number=from_wa)

            if advertiser.whatsapp_number or advertiser.phone:
                owner_wa = advertiser.whatsapp_number or advertiser.phone
                await _send_wa(owner_wa, owner_notify)

            return {"message": "ok"}

    # Coupon redemption intent
    if is_redeem_intent(body_text):
        contact_result = await db.execute(
            select(Contact).where(
                Contact.advertiser_id == advertiser.id,
                Contact.phone == from_number,
            )
        )
        contact = contact_result.scalar_one_or_none()
        if contact:
            coupon_result = await db.execute(
                select(Coupon).where(
                    Coupon.advertiser_id == advertiser.id,
                    Coupon.contact_id == contact.id,
                    Coupon.redeemed_at.is_(None),
                ).order_by(Coupon.created_at.desc())
            )
            coupon = coupon_result.scalars().first()
            if coupon and not is_expired(coupon.expires_at):
                from datetime import datetime, timezone
                coupon.redeemed_at = datetime.now(timezone.utc)
                coupon.redeemed_by_phone = from_number
                coupon.used_count += 1

                if coupon.campaign_id:
                    camp_result = await db.execute(
                        select(Campaign).where(Campaign.id == coupon.campaign_id)
                    )
                    camp = camp_result.scalar_one_or_none()
                    if camp:
                        stats = dict(camp.stats or {})
                        stats["coupons_redeemed"] = stats.get("coupons_redeemed", 0) + 1
                        camp.stats = stats

                await db.commit()
                redeem_reply = (
                    f"✅ ¡Cupón *{coupon.code}* canjeado exitosamente!\n"
                    f"Muestra este mensaje al llegar.\n"
                    f"Beneficio: {coupon.description or 'Descuento especial'} 🎉"
                )
            elif coupon and is_expired(coupon.expires_at):
                redeem_reply = "⏰ Tu cupón ya expiró. ¡Pero pronto tendremos nuevas ofertas para ti!"
            else:
                redeem_reply = "No encontré un cupón activo para ti. Escríbenos si crees que es un error."

            out_msg = Message(
                advertiser_id=advertiser.id,
                contact_id=contact.id,
                direction="outbound",
                content=redeem_reply,
                status="queued",
            )
            db.add(out_msg)
            await db.commit()
            from app.workers.tasks import update_contact_engagement_score
            sid_c, err_c = await _send_wa(
                from_number, redeem_reply,
                from_number=advertiser.whatsapp_number,
            )
            if sid_c:
                out_msg.status = "sent"
                out_msg.twilio_sid = sid_c
                out_msg.sent_at = datetime.now(timezone.utc)
            else:
                out_msg.status = "failed"
                out_msg.error_code = err_c
            await db.commit()
            update_contact_engagement_score.apply_async(
                args=[str(contact.id)],
                queue="whatsapp",
                countdown=10,
            )
            return {"message": "ok"}

    # Get or create contact
    contact_result = await db.execute(
        select(Contact).where(
            Contact.advertiser_id == advertiser.id,
            Contact.phone.in_(from_candidates),
        )
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        contact = Contact(
            advertiser_id=advertiser.id,
            name=from_number,
            phone=from_number,
            source="landing",
        )
        db.add(contact)
        await db.flush()
        _is_new_contact = True
    else:
        _is_new_contact = False

    # Voces del Barrio — Save customer story from audio
    if audio_transcription and media_url and advertiser:
        voces_result = await db.execute(
            select(Campaign).where(
                Campaign.advertiser_id == advertiser.id,
                Campaign.type == "voces",
                Campaign.status.in_(["running", "scheduled"]),
            ).limit(1)
        )
        voces_campaign = voces_result.scalar_one_or_none()
        if voces_campaign:
            story = CustomerStory(
                advertiser_id=advertiser.id,
                contact_id=contact.id,
                campaign_id=voces_campaign.id,
                media_url=media_url,
                transcription=audio_transcription,
            )
            db.add(story)

    # Save inbound message (con unique constraint en twilio_sid para idempotencia)
    try:
        msg = Message(
            advertiser_id=advertiser.id,
            contact_id=contact.id,
            direction="inbound",
            content=body_text,
            status="delivered",
            twilio_sid=message_sid or None,
        )
        db.add(msg)
        await db.flush()
    except IntegrityError:
        await db.rollback()
        logger.info("[WEBHOOK] Duplicate webhook ignored (twilio_sid=%s)", message_sid)
        return {"message": "ok"}

    # Get or create conversation
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.advertiser_id == advertiser.id,
            Conversation.contact_id == contact.id,
            Conversation.status == "active",
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        conv = Conversation(
            advertiser_id=advertiser.id,
            contact_id=contact.id,
            messages=[],
            lead_score="cold",
        )
        db.add(conv)
        await db.flush()
    else:
        msg_count = len(conv.messages) if conv.messages else 0
        new_score = calculate_lead_score(body_text, msg_count)
        if new_score:
            conv.lead_score = new_score
    conv.last_activity = func.now()

    contact_name = (contact.name or "Cliente").split()[0] if contact else "Cliente"

    # Order state machine
    pending_order_result = await db.execute(
        select(Order).where(
            Order.advertiser_id == advertiser.id,
            Order.contact_id == contact.id,
            Order.state.not_in(["confirmed", "cancelled"]),
        ).order_by(Order.created_at.desc())
    )
    pending_order = pending_order_result.scalars().first()

    order_reply: str | None = None

    if pending_order:
        if pending_order.state == "pending_confirmation":
            normalized_msg = body_text.lower().strip()
            affirm_words = {"sí", "si", "s", "yes", "y", "ok", "dale", "claro", "adelante", "por supuesto"}
            is_affirmative = (
                normalized_msg in affirm_words
                or any(normalized_msg.startswith(f"{w} ") for w in ["sí", "si", "yes", "ok", "dale"])
            )
            if is_affirmative:
                pending_order.state = "collecting_name"
                _tpl = await get_template(db, str(advertiser.id), "Pedido", "order_name")
                contact_data = {"name": contact.name or "amigo", "city": ""}
                adv_data = {"business_name": advertiser.business_name or "nuestro negocio", "city": ""}
                order_reply = personalize_message(_tpl, contact_data, adv_data) if _tpl else (
                    "¡Excelente! 🎉\n"
                    "Para completarlo, ¿a qué nombre va el pedido?"
                )
            else:
                pending_order.state = "cancelled"
                await db.flush()

        elif pending_order.state == "collecting_name":
            pending_order.customer_name = body_text.strip()
            pending_order.state = "collecting_address"
            _tpl = await get_template(db, str(advertiser.id), "Pedido", "order_address")
            _first = pending_order.customer_name.split()[0]
            contact_data = {"name": _first, "city": ""}
            adv_data = {"business_name": "", "city": ""}
            order_reply = personalize_message(_tpl, contact_data, adv_data) if _tpl else (
                f"Perfecto, {_first} 👍\n"
                "¿Cuál es tu dirección de entrega? 📍"
            )
        elif pending_order.state == "collecting_address":
            pending_order.delivery_address = body_text.strip()
            pending_order.state = "collecting_payment"
            _tpl = await get_template(db, str(advertiser.id), "Pedido", "order_payment")
            order_reply = personalize_message(_tpl, {"name": "", "city": ""}, {"business_name": "", "city": ""}) if _tpl else (
                "¡Anotado! 📝 ¿Cómo prefieres pagar?\n"
                "Responde: *Efectivo*, *Tarjeta* o *Transferencia* 💳"
            )
        elif pending_order.state == "collecting_payment":
            from datetime import datetime, timezone as tz
            pending_order.payment_method = body_text.strip()
            pending_order.state = "confirmed"
            pending_order.confirmed_at = datetime.now(tz.utc)
            await db.flush()

            _tpl = await get_template(db, str(advertiser.id), "Pedido", "order_confirmed")
            _oc = {
                "nombre": pending_order.customer_name or "Cliente",
                "order_number": f"{pending_order.order_number:04d}",
                "items": pending_order.items_raw or "",
                "direccion": pending_order.delivery_address or "",
                "pago": pending_order.payment_method or "",
                "city": "",
            }
            order_reply = personalize_message(_tpl, _oc, {"business_name": "", "city": ""}) if _tpl else (
                f"✅ *Pedido #{pending_order.order_number:04d} confirmado*\n\n"
                f"🛒 {pending_order.items_raw}\n"
                f"👤 {pending_order.customer_name}\n"
                f"📍 {pending_order.delivery_address}\n"
                f"💳 {pending_order.payment_method}\n\n"
                "¡Gracias! En breve te contactamos para confirmar el tiempo de entrega 🚀"
            )

            _tpl_owner = await get_template(db, str(advertiser.id), "Pedido", "order_owner_notify")
            _on = {
                "nombre": pending_order.customer_name or "Cliente",
                "order_number": f"{pending_order.order_number:04d}",
                "items": pending_order.items_raw or "",
                "telefono": from_number,
                "direccion": pending_order.delivery_address or "",
                "pago": pending_order.payment_method or "",
                "city": "",
            }
            wa_notify = personalize_message(_tpl_owner, _on, {"business_name": "", "city": ""}) if _tpl_owner else (
                f"📦 *NUEVO PEDIDO #{pending_order.order_number:04d}*\n"
                f"────────────────\n"
                f"🛒 {pending_order.items_raw}\n"
                f"👤 Cliente: {pending_order.customer_name}\n"
                f"📱 WhatsApp: {from_number}\n"
                f"📍 Dirección: {pending_order.delivery_address}\n"
                f"💳 Pago: {pending_order.payment_method}\n"
                f"────────────────\n"
                f"Responde a este número para contactar al cliente."
            )
            if advertiser.phone or advertiser.whatsapp_number:
                from app.services.twilio_service import send_whatsapp
                owner_number = advertiser.whatsapp_number or advertiser.phone
                await send_whatsapp(
                    to=owner_number,
                    body=wa_notify,
                )

            from app.core.email import send_new_order_email
            import asyncio
            asyncio.create_task(
                send_new_order_email(
                    to=advertiser.email,
                    order_number=pending_order.order_number,
                    business_name=advertiser.business_name or "Tu negocio",
                    items_raw=pending_order.items_raw or "",
                    customer_name=pending_order.customer_name or "",
                    customer_phone=from_number,
                    delivery_address=pending_order.delivery_address or "",
                    payment_method=pending_order.payment_method or "",
                )
            )

        elif pending_order.state.startswith("plan_"):
            if pending_order.state == "plan_pending_confirmation":
                normalized_msg = body_text.lower().strip()
                affirm_words = {"sí", "si", "s", "yes", "y", "ok", "dale", "claro", "adelante", "por supuesto"}
                is_affirmative = (
                    normalized_msg in affirm_words
                    or any(normalized_msg.startswith(f"{w} ") for w in ["sí", "si", "yes", "ok", "dale"])
                )
                if is_affirmative:
                    pending_order.state = "plan_collecting_name"
                    _tpl = await get_template(db, str(advertiser.id), "Plan", "plan_name")
                    order_reply = personalize_message(_tpl, {"name": "", "city": ""}, {"business_name": "", "city": ""}) if _tpl else (
                        "¡Excelente! 🎉 ¿A qué nombre te registramos?"
                    )
                else:
                    pending_order.state = "cancelled"
                    await db.flush()

            elif pending_order.state == "plan_collecting_name":
                pending_order.customer_name = body_text.strip()
                pending_order.state = "plan_collecting_datetime"
                first_name = pending_order.customer_name.split()[0]
                _tpl = await get_template(db, str(advertiser.id), "Plan", "plan_datetime")
                _pd = {"nombre": first_name, "primer_nombre": first_name, "city": ""}
                order_reply = personalize_message(_tpl, _pd, {"business_name": "", "city": ""}) if _tpl else (
                    f"Perfecto, {first_name} 👍\n"
                    "¿Qué día y hora prefieres para tu cita de activación?\n"
                    "Por ejemplo: *Mañana a las 10 am* o *Viernes a las 4 pm* 📅"
                )

            elif pending_order.state == "plan_collecting_datetime":
                from datetime import datetime, timezone as tz
                pending_order.notes = body_text.strip()
                pending_order.state = "plan_confirmed"
                pending_order.confirmed_at = datetime.now(tz.utc)
                await db.flush()

                plan_name = pending_order.items_raw or "Plan"
                first_name = pending_order.customer_name.split()[0] if pending_order.customer_name else "Cliente"

                _tpl = await get_template(db, str(advertiser.id), "Plan", "plan_confirmed")
                _pc = {"nombre": pending_order.customer_name or "Cliente", "primer_nombre": first_name, "plan": plan_name.replace("Plan ", ""), "fecha": pending_order.notes or "", "city": ""}
                order_reply = personalize_message(_tpl, _pc, {"business_name": "", "city": ""}) if _tpl else (
                    f"✅ *{plan_name} registrado*\n\n"
                    f"👤 {pending_order.customer_name}\n"
                    f"📅 Preferencia: {pending_order.notes}\n\n"
                    "Te contactaremos pronto para confirmar los detalles y activar tu plan. ¡Gracias! 🚀"
                )

                wa_notify = (
                    f"🆕 *NUEVA VENTA DE PLAN*\n"
                    f"────────────────\n"
                    f"📋 {plan_name}\n"
                    f"👤 Cliente: {pending_order.customer_name}\n"
                    f"📱 WhatsApp: {from_number}\n"
                    f"📅 Cita preferida: {pending_order.notes}\n"
                    f"────────────────\n"
                    f"Contacta al cliente para activar su plan."
                )
                if advertiser.phone or advertiser.whatsapp_number:
                    from app.services.twilio_service import send_whatsapp
                    owner_number = advertiser.whatsapp_number or advertiser.phone
                    await send_whatsapp(
                        to=owner_number,
                        body=wa_notify,
                    )

    elif not pending_order:
        detected_plan = detect_plan_purchase_intent(body_text)
        if detected_plan:
            count_result = await db.execute(
                select(func.count()).select_from(Order).where(
                    Order.advertiser_id == advertiser.id
                )
            )
            order_count = count_result.scalar() or 0

            new_order = Order(
                advertiser_id=advertiser.id,
                contact_id=contact.id,
                items_raw=f"Plan {detected_plan.capitalize()}",
                state="plan_pending_confirmation",
                order_number=order_count + 1,
            )
            db.add(new_order)
            await db.flush()
            pending_order = new_order

            req_notify = (
                f"🎯 *NUEVA SOLICITUD DE PLAN*\n"
                f"────────────────\n"
                f"📋 Plan: {detected_plan.capitalize()}\n"
                f"👤 Cliente: {contact_name}\n"
                f"📱 WhatsApp: {from_number}\n"
                f"────────────────\n"
                f"Abre el inbox para dar seguimiento."
            )
            if advertiser.phone or advertiser.whatsapp_number:
                from app.services.twilio_service import send_whatsapp
                owner_number = advertiser.whatsapp_number or advertiser.phone
                try:
                    await send_whatsapp(to=owner_number, body=req_notify)
                except Exception:
                    logger.warning("[PLAN] Failed to send plan request notification", exc_info=True)

            _tpl = await get_template(db, str(advertiser.id), "Plan", "plan_confirm")
            _pi = {"nombre": contact_name, "plan": detected_plan.capitalize(), "city": ""}
            order_reply = personalize_message(_tpl, _pi, {"business_name": "", "city": ""}) if _tpl else (
                f"¡Excelente elección! 💪\n"
                f"¿Confirmas que quieres el *Plan {detected_plan.capitalize()}*?\n"
                "Responde *Sí* o *No* 😊"
            )
        else:
            is_order = detect_order_intent(body_text)
            if is_order:
                count_result = await db.execute(
                    select(func.count()).select_from(Order).where(
                        Order.advertiser_id == advertiser.id
                    )
                )
                order_count = count_result.scalar() or 0

                new_order = Order(
                    advertiser_id=advertiser.id,
                    contact_id=contact.id,
                    items_raw=body_text,
                    state="pending_confirmation",
                    order_number=order_count + 1,
                )
                db.add(new_order)
                await db.flush()
                pending_order = new_order

                _tpl = await get_template(db, str(advertiser.id), "Pedido", "order_confirm")
                order_reply = personalize_message(_tpl, {"name": "", "city": ""}, {"business_name": "", "city": ""}) if _tpl else (
                    "¡Gracias por tu interés! 🛒\n"
                    "¿Te gustaría hacer un pedido? Responde *Sí* o *No* 😊"
                )

    if order_reply is not None:
        updated_msgs = conv.messages + [
            {"role": "user", "content": body_text},
            {"role": "assistant", "content": order_reply},
        ]
        conv.messages = updated_msgs[-40:]
        conv.last_activity = func.now()

        out_msg = Message(
            advertiser_id=advertiser.id,
            contact_id=contact.id,
            direction="outbound",
            content=order_reply,
            status="queued",
        )
        db.add(out_msg)
        await db.commit()

        from app.workers.tasks import update_contact_engagement_score

        sid_o, err_o = await _send_wa(
            from_number, order_reply,
            from_number=advertiser.whatsapp_number,
        )
        if sid_o:
            out_msg.status = "sent"
            out_msg.twilio_sid = sid_o
            out_msg.sent_at = datetime.now(timezone.utc)
        else:
            out_msg.status = "failed"
            out_msg.error_code = err_o
        await db.commit()
        update_contact_engagement_score.apply_async(
            args=[str(contact.id)],
            queue="whatsapp",
            countdown=10,
        )
        return {"message": "ok"}

    # Build conversation history
    history = conv.messages[-40:] if conv.messages else []

    rag_query = body_text
    if audio_transcription:
        rag_query = f"[El cliente envió un mensaje de voz. Transcripción: {audio_transcription}]"

    try:
        reply = await answer_with_rag(
            advertiser_id=str(advertiser.id),
            query=rag_query,
            conversation_history=history,
            db=db,
            business_name=advertiser.business_name or "el negocio",
            bot_name=advertiser.bot_name or "Asistente",
            bot_personality=advertiser.bot_personality or "amigable y profesional",
        )
    except Exception as e:
        logger.error("[WEBHOOK] RAG/Claude error: %s", e, exc_info=True)
        biz = advertiser.business_name or "el negocio"
        name = advertiser.bot_name or "Asistente"
        personality = advertiser.bot_personality or "Estoy aquí para ayudarte con información sobre nuestros servicios y productos."
        reply = (
            f"Hola! Soy {name} de {biz}. "
            f"{personality} "
            "¿En qué puedo ayudarte hoy? 😊"
        )

    updated_msgs = conv.messages + [
        {"role": "user", "content": body_text},
        {"role": "assistant", "content": reply},
    ]
    conv.messages = updated_msgs[-40:]
    conv.last_activity = func.now()

    out_msg = Message(
        advertiser_id=advertiser.id,
        contact_id=contact.id,
        direction="outbound",
        content=reply,
        status="queued",
    )
    db.add(out_msg)
    await db.commit()

    from app.workers.tasks import send_welcome_cuna, update_contact_engagement_score, trigger_automation_for_contact, auto_tag_contact_from_conversation

    sid, err = await _send_wa(
        from_number, reply,
        from_number=advertiser.whatsapp_number,
    )
    if sid:
        out_msg.status = "sent"
        out_msg.twilio_sid = sid
        out_msg.sent_at = datetime.now(timezone.utc)
    else:
        out_msg.status = "failed"
        out_msg.error_code = err
    await db.commit()

    try:
        update_contact_engagement_score.apply_async(
            args=[str(contact.id)],
            queue="whatsapp",
            countdown=10,
        )
    except Exception:
        logger.warning("[WEBHOOK] Failed to queue engagement score update")

    if _is_new_contact and advertiser.business_name:
        try:
            send_welcome_cuna.apply_async(
                kwargs={
                    "advertiser_id": str(advertiser.id),
                    "to": from_number,
                    "business_name": advertiser.business_name,
                    "from_number": advertiser.whatsapp_number,
                },
                queue="whatsapp",
                countdown=10,
            )
        except Exception:
            logger.warning("[WEBHOOK] Failed to queue welcome cuna")
        try:
            trigger_automation_for_contact.apply_async(
                args=[str(contact.id), str(advertiser.id), "new_contact"],
                queue="whatsapp",
                countdown=15,
            )
        except Exception:
            logger.warning("[WEBHOOK] Failed to queue automation")
    else:
        try:
            trigger_automation_for_contact.apply_async(
                args=[str(contact.id), str(advertiser.id), "keyword", body_text],
                queue="whatsapp",
                countdown=5,
            )
        except Exception:
            logger.warning("[WEBHOOK] Failed to queue automation")

    try:
        auto_tag_contact_from_conversation.apply_async(
            args=[str(contact.id)],
            queue="whatsapp",
            countdown=30,
        )
    except Exception:
        logger.warning("[WEBHOOK] Failed to queue auto-tag")

    return {"message": "ok"}
