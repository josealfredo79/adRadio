"""
Twilio incoming webhook — handle inbound WhatsApp messages.
"""
import hashlib
import hmac
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
from app.services.number_pool_service import assign_pool_number, release_pool_number
from app.services.rag_service import answer_with_rag
from app.services.claude_service import detect_order_intent
from app.api.v1.webhooks_pkg.lead_score import calculate_lead_score

logger = logging.getLogger(__name__)


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
                base_url = "https://adradio-production-51a9.up.railway.app"
                alt_url = re.sub(r"^https?://[^/]+", base_url, url)
                if alt_url == url or not _validate_twilio_signature(alt_url, form_data, signature):
                    logger.warning("[WEBHOOK] Signature validation failed — url=%s alt_url=%s", url, alt_url)
        elif not settings.DEBUG:
            logger.warning("[WEBHOOK] Missing X-Twilio-Signature header — request from %s", request.client.host if request.client else "unknown")

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
    contact_from_result = await db.execute(
        select(Contact).where(Contact.phone == from_number).order_by(Contact.created_at.desc())
    )
    existing_contact = contact_from_result.scalars().first()
    if existing_contact:
        advertiser = await db.get(User, existing_contact.advertiser_id)
        logger.warning("[WEBHOOK] Step1: contact found — advertiser=%s biz=%s", advertiser.id if advertiser else None, advertiser.business_name if advertiser else None)
    else:
        logger.warning("[WEBHOOK] Step1: NO contact for From=%s", from_number)

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
                Contact.phone == from_number,
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
            from app.services.twilio_service import send_whatsapp as _send_wa
            normalized = body_text.strip().lower()
            if normalized in ("1", "si", "sí", "s", "yes", "y", "claro", "por supuesto", "reagendar"):
                reschedule_appt.awaiting_reschedule = False
                await db.commit()
                reply = (
                    "¡Genial! 📅\n"
                    "Por favor escríbeme qué día y hora prefieres esta semana "
                    "y revisaré la disponibilidad para agendarte."
                )
                await _send_wa(from_number, reply, from_number=advertiser.whatsapp_number)
                return {"message": "ok"}
            elif normalized in ("2", "no", "n", "nop", "cancelar"):
                reschedule_appt.awaiting_reschedule = False
                await db.commit()
                reply = "Entendido 👍. ¡Escríbenos cuando estés listo/a!"
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
            from app.services.twilio_service import send_whatsapp as _send_wa
            hora = pending_appt.scheduled_at.strftime("%I:%M %p").lstrip("0")
            fecha = pending_appt.scheduled_at.strftime("%A %d de %B")
            biz_name = advertiser.business_name or "el negocio"
            from_wa = advertiser.whatsapp_number

            if normalized in confirm_keywords:
                pending_appt.status = "confirmed"
                pending_appt.awaiting_confirmation = False
                _appt_reply = (
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
                _appt_reply = (
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
            from app.workers.tasks import send_whatsapp_message, update_contact_engagement_score
            send_whatsapp_message.apply_async(
                args=[str(out_msg.id), from_number, redeem_reply],
                countdown=2,
            )
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
            Contact.phone == from_number,
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
                order_reply = (
                    "¡Excelente! 🎉\n"
                    "Para completarlo, ¿a qué nombre va el pedido?"
                )
            else:
                pending_order.state = "cancelled"
                await db.flush()

        elif pending_order.state == "collecting_name":
            pending_order.customer_name = body_text.strip()
            pending_order.state = "collecting_address"
            order_reply = (
                f"Perfecto, {pending_order.customer_name.split()[0]} 👍\n"
                "¿Cuál es tu dirección de entrega? 📍"
            )
        elif pending_order.state == "collecting_address":
            pending_order.delivery_address = body_text.strip()
            pending_order.state = "collecting_payment"
            order_reply = (
                "¡Anotado! 📝 ¿Cómo prefieres pagar?\n"
                "Responde: *Efectivo*, *Tarjeta* o *Transferencia* 💳"
            )
        elif pending_order.state == "collecting_payment":
            from datetime import datetime, timezone as tz
            pending_order.payment_method = body_text.strip()
            pending_order.state = "confirmed"
            pending_order.confirmed_at = datetime.now(tz.utc)
            await db.flush()

            order_reply = (
                f"✅ *Pedido #{pending_order.order_number:04d} confirmado*\n\n"
                f"🛒 {pending_order.items_raw}\n"
                f"👤 {pending_order.customer_name}\n"
                f"📍 {pending_order.delivery_address}\n"
                f"💳 {pending_order.payment_method}\n\n"
                "¡Gracias! En breve te contactamos para confirmar el tiempo de entrega 🚀"
            )

            wa_notify = (
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

    elif not pending_order:
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

            order_reply = (
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

        from app.services.twilio_service import send_whatsapp_buttons
        from app.workers.tasks import send_whatsapp_message, update_contact_engagement_score

        button_sid = settings.TWILIO_ORDER_CONFIRM_BUTTONS_SID
        if button_sid:
            sid, err = await send_whatsapp_buttons(
                to=contact.phone,
                body=order_reply,
                template_sid=button_sid,
                variables={"1": contact_name},
                from_number=advertiser.whatsapp_number,
            )
            if not sid:
                logger.warning("[ORDER] Button template failed, falling back to text: %s", err)
                send_whatsapp_message.apply_async(
                    args=[str(out_msg.id), from_number, order_reply],
                    queue="whatsapp",
                    countdown=2,
                )
        else:
            send_whatsapp_message.apply_async(
                args=[str(out_msg.id), from_number, order_reply],
                queue="whatsapp",
                countdown=2,
            )
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
        reply = (
            f"Hola! Soy {name} de {biz}. "
            "En este momento tengo problemas para consultar mi base de conocimiento. "
            "¿Puedes intentarlo de nuevo en unos minutos? 😊"
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

    from app.workers.tasks import send_whatsapp_message, send_welcome_cuna, update_contact_engagement_score
    from app.services.twilio_service import send_whatsapp as _send_wa_direct

    try:
        send_whatsapp_message.apply_async(
            args=[str(out_msg.id), from_number, reply],
            queue="whatsapp",
        )
    except Exception as celery_err:
        logger.error("[WEBHOOK] Celery unavailable, sending direct: %s", celery_err)
        sid_direct, err_direct = await _send_wa_direct(
            from_number, reply,
            from_number=advertiser.whatsapp_number,
        )
        if sid_direct:
            out_msg.status = "sent"
            out_msg.twilio_sid = sid_direct
            out_msg.sent_at = datetime.now(timezone.utc)
        else:
            out_msg.status = "failed"
            out_msg.error_code = err_direct
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
