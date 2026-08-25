"""
Bot pipeline for an inbound WhatsApp message, decoupled from the transport
that received it. The Meta webhook (meta_incoming.py) parses the Graph API
payload, resolves the advertiser, and builds an `InboundMessage` + a `send`
closure bound to meta_service. Everything from there on (STOP-words,
appointment state machine, coupon redemption, order/plan state machine, RAG
fallback, message persistence, follow-up jobs) lives here.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.coupon import Coupon
from app.models.customer_story import CustomerStory
from app.models.message import Message
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.user import User
from app.services.appointment_booking_service import handle_appointment_booking
from app.services.catalog_service import get_active_products, handle_catalog_query, match_products_in_text
from app.services.claude_service import (
    detect_order_intent,
    detect_plan_purchase_intent,
    format_time_gap_note,
    personalize_message,
)
from app.services.coupon_service import is_expired, is_redeem_intent
from app.services.handoff_service import matches_handoff_intent
from app.services.rag_service import answer_with_rag
from app.services.template_lookup import get_template
from app.services.lead_score import calculate_lead_score
from app.services.realtime import publish_conversation_event

logger = logging.getLogger(__name__)

# (external_id, error) — same shape meta_service already returns.
SendFn = Callable[[str, str], Awaitable[tuple[str | None, str | None]]]


@dataclass
class InboundMessage:
    advertiser: User
    from_number: str
    body_text: str
    audio_transcription: str | None = None
    media_url: str | None = None
    external_message_id: str | None = None


def _phone_candidates(from_number: str) -> list[str]:
    """MX 521/52 prefix variants — same normalization used for advertiser resolution."""
    from_clean = from_number.lstrip("+").replace(" ", "")
    candidates = [from_number]
    if from_clean.startswith("521"):
        candidates.append("+52" + from_clean[3:])
    elif from_clean.startswith("52"):
        candidates.append("+521" + from_clean[2:])
    return candidates


async def process_inbound_message(
    db: AsyncSession,
    msg: InboundMessage,
    send: SendFn,
    send_owner: SendFn,
) -> dict[str, str]:
    """
    Run the full bot pipeline for an already-resolved advertiser + inbound text.

    `send` sends customer-facing replies; `send_owner` sends the advertiser's
    owner-notification messages. Kept as two separate callables even though
    the Meta adapter currently binds both to the same underlying function —
    a future channel could reasonably want owner notifications routed
    differently from customer replies.
    """
    advertiser = msg.advertiser
    from_number = msg.from_number
    body_text = msg.body_text
    audio_transcription = msg.audio_transcription
    media_url = msg.media_url
    external_message_id = msg.external_message_id
    from_candidates = _phone_candidates(from_number)

    # Idempotency — skip if this message was already processed
    if external_message_id:
        existing = await db.execute(
            select(Message).where(Message.wa_message_id == external_message_id).limit(1)
        )
        if existing.scalar_one_or_none():
            return {"message": "ok"}

    # Human handoff — once a conversation is escalated (agent clicked "Pausar
    # bot" in the inbox), the bot must not touch it at all: no STOP-word
    # auto-unsubscribe, no appointment/order state machines, no RAG reply.
    # Just log the inbound message so it shows up for the human and stop.
    existing_contact_result = await db.execute(
        select(Contact).where(
            Contact.advertiser_id == advertiser.id,
            Contact.phone.in_(from_candidates),
        )
    )
    existing_contact = existing_contact_result.scalar_one_or_none()
    if existing_contact:
        escalated_result = await db.execute(
            select(Conversation).where(
                Conversation.advertiser_id == advertiser.id,
                Conversation.contact_id == existing_contact.id,
                Conversation.status == "escalated",
            )
        )
        escalated_conv = escalated_result.scalar_one_or_none()
        if escalated_conv:
            try:
                handoff_msg = Message(
                    advertiser_id=advertiser.id,
                    contact_id=existing_contact.id,
                    direction="inbound",
                    content=body_text,
                    status="delivered",
                    wa_message_id=external_message_id or None,
                )
                db.add(handoff_msg)
                await db.flush()
            except IntegrityError:
                await db.rollback()
            else:
                escalated_conv.last_activity = func.now()
                await db.commit()
                await publish_conversation_event(advertiser.id, {"type": "message", "contact_id": str(existing_contact.id)})
            return {"message": "ok"}

    # Capa 12 anti-baneo: opt-out por palabra clave. Un STOP ignorado (por un
    # desfase de formato de número, o por puntuación/espacios que rompen el
    # match exacto) sigue enviándole campañas a alguien que pidió baja — la
    # causa #1 de reportes de spam que hunden el quality rating de la cuenta.
    stop_words = {"baja", "stop", "no quiero", "cancelar", "salir"}
    normalized_stop_body = body_text.strip().lower().rstrip(".!¡¿? ")
    if normalized_stop_body in stop_words:
        contact_result = await db.execute(
            select(Contact).where(
                Contact.advertiser_id == advertiser.id,
                Contact.phone.in_(from_candidates),
            )
        )
        contact = contact_result.scalar_one_or_none()
        if contact:
            contact.status = "unsubscribed"
            contact.engagement_score = 0
            await db.commit()
            try:
                await send(
                    from_number,
                    "Listo, no volverás a recibir mensajes nuestros. "
                    "Si cambias de opinión, escríbenos cuando quieras 🙏",
                )
            except Exception:
                logger.warning("[STOP] Failed to send opt-out confirmation to %s", from_number, exc_info=True)
        return {"message": "ok"}

    # Appointment reschedule handler
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
            await send(from_number, reply)
            return {"message": "ok"}
        elif normalized in ("2", "no", "n", "nop", "cancelar"):
            reschedule_appt.awaiting_reschedule = False
            await db.commit()
            _tpl = await get_template(db, str(advertiser.id), "Cita", "appt_reschedule_no")
            reply = personalize_message(_tpl, {"name": "", "city": ""}, {"business_name": "", "city": ""}) if _tpl else "Entendido 👍. ¡Escríbenos cuando estés listo/a!"
            await send(from_number, reply)
            return {"message": "ok"}

    # Appointment confirmation handler
    _appt_reply: str | None = None
    confirm_keywords = {"1", "si", "sí", "yes", "confirmo", "confirmar", "✅", "ok", "dale"}
    cancel_keywords = {"2", "no", "cancela", "cancelar", "cancelar cita", "no puedo", "❌"}
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
            hora = pending_appt.scheduled_at.strftime("%I:%M %p").lstrip("0")
            fecha = pending_appt.scheduled_at.strftime("%A %d de %B")
            biz_name = advertiser.business_name or "el negocio"

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
            await send(from_number, _appt_reply)

            if advertiser.whatsapp_number or advertiser.phone:
                owner_wa = advertiser.whatsapp_number or advertiser.phone
                await send_owner(owner_wa, owner_notify)

            return {"message": "ok"}

    # Capa 16 anti-baneo: confirmación de cuña de radio ofrecida vía
    # plantilla (ver `_offer_or_send_radio_audio` en campaign_ops.py). Una
    # plantilla enviada por el negocio NO reabre la ventana de 24h por sí
    # sola — solo lo hace una respuesta real del cliente — así que en vez de
    # asumir que la ventana ya está abierta después de mandar la plantilla,
    # se le pregunta al cliente y el audio solo se envía tras su respuesta
    # real (un tap en el botón cuenta como respuesta real ante Meta). Se
    # revisa aquí, antes que cualquier otro estado, pero solo actúa si de
    # verdad hay un audio pendiente para este contacto — si no lo hay, un
    # "sí"/"no" cualquiera sigue de largo a los demás manejadores.
    normalized_audio_reply = body_text.strip().lower().rstrip(".!¡¿? ")
    audio_confirm_words = {"si, escuchalo", "sí, escúchalo", "si", "sí", "s", "yes", "escuchar", "escúchalo", "escuchalo"}
    audio_decline_words = {"ahora no", "no", "no gracias", "despues", "después"}
    if normalized_audio_reply in audio_confirm_words or normalized_audio_reply in audio_decline_words:
        audio_contact_result = await db.execute(
            select(Contact).where(
                Contact.advertiser_id == advertiser.id,
                Contact.phone.in_(from_candidates),
            )
        )
        audio_contact = audio_contact_result.scalar_one_or_none()
        if audio_contact:
            pending_result = await db.execute(
                select(Message).where(
                    Message.advertiser_id == advertiser.id,
                    Message.contact_id == audio_contact.id,
                    Message.status == "queued",
                    Message.content.like("[AUDIO-PENDING]%"),
                ).order_by(Message.created_at.desc()).limit(1)
            )
            pending_msg = pending_result.scalar_one_or_none()
            if pending_msg:
                if normalized_audio_reply in audio_confirm_words:
                    from app.services.meta_service import send_whatsapp_media

                    pending_audio_url = pending_msg.content.removeprefix("[AUDIO-PENDING] ")
                    pending_script = None
                    if pending_msg.campaign_id:
                        camp_result = await db.execute(
                            select(Campaign).where(Campaign.id == pending_msg.campaign_id)
                        )
                        camp = camp_result.scalar_one_or_none()
                        if camp:
                            pending_script = (camp.ab_test or {}).get("radio_script")

                    sid_au, err_au = await send_whatsapp_media(
                        from_number, pending_audio_url, body=pending_script or "", advertiser=advertiser,
                    )
                    pending_msg.status = "sent" if sid_au else "failed"
                    pending_msg.wa_message_id = sid_au
                    pending_msg.error_code = err_au
                    pending_msg.sent_at = datetime.now(timezone.utc) if sid_au else None
                    if sid_au:
                        advertiser.messages_remaining -= 1
                        audio_contact.last_campaign_sent_at = datetime.now(timezone.utc)
                        confirm_reply = "¡Aquí tienes! 🎙️"
                    else:
                        confirm_reply = "Uy, tuvimos un problema enviándolo. Lo reintentamos en breve 🙏"
                else:
                    pending_msg.status = "failed"
                    pending_msg.error_code = "declined_by_contact"
                    confirm_reply = "Entendido 👍 Aquí estamos si cambias de opinión."
                await db.commit()
                try:
                    await send(from_number, confirm_reply)
                except Exception:
                    logger.warning("[RADIO-OPTIN] Failed to send confirmation reply to %s", from_number, exc_info=True)
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
            sid_c, err_c = await send(from_number, redeem_reply)
            if sid_c:
                out_msg.status = "sent"
                out_msg.wa_message_id = sid_c
                out_msg.sent_at = datetime.now(timezone.utc)
            else:
                out_msg.status = "failed"
                out_msg.error_code = err_c
            await db.commit()
            await publish_conversation_event(advertiser.id, {"type": "message", "contact_id": str(contact.id)})
            update_contact_engagement_score.apply_async(
                args=[str(contact.id)],
                queue="whatsapp",
                countdown=30,
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

    # Voces del Barrio — save customer story from audio
    if audio_transcription and media_url:
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

    # Save inbound message (unique constraint on wa_message_id for idempotency)
    try:
        msg_row = Message(
            advertiser_id=advertiser.id,
            contact_id=contact.id,
            direction="inbound",
            content=body_text,
            status="delivered",
            wa_message_id=external_message_id or None,
        )
        db.add(msg_row)
        await db.flush()
    except IntegrityError:
        await db.rollback()
        logger.info("[PIPELINE] Duplicate webhook ignored (external_message_id=%s)", external_message_id)
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
    # Captured before conv.last_activity gets overwritten to "now" below —
    # this is the real previous-message timestamp used for the time-gap note.
    # Also sidesteps a real MissingGreenlet crash found in production
    # 2026-08-13: reading an ORM attribute later in this function (after other
    # commits may have expired it) requires an async reload that a bare
    # attribute access can't do — a plain Python value captured here has no
    # such problem.
    previous_last_activity = conv.last_activity if conv else None
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

    # Reset anti-suppression when contact replies
    contact.last_interaction = func.now()
    contact.failed_send_count = 0
    contact.suppressed_until = None
    # A real reply from this number is the strongest consent signal there is —
    # unblocks future cold-window template sends regardless of import origin.
    contact.consent_status = "confirmed"

    contact_name = (contact.name or "Cliente").split()[0]

    # Escalado a humano pedido por el cliente — mismo patrón de "silencio
    # total" que ya usa el botón manual "Pausar bot" (ver el gate de handoff
    # al inicio de esta función), pero disparado por el propio cliente. El
    # bot en AdRadio solo genera texto libre (nunca decide "escalar" como
    # acción estructurada), así que este regex de respaldo es hoy la única
    # vía — ver handoff_service.py para el porqué del patrón.
    if matches_handoff_intent(body_text):
        conv.status = "escalated"
        farewell = "Claro, en un momento te atiende alguien del equipo 🙌"
        out_msg = Message(
            advertiser_id=advertiser.id,
            contact_id=contact.id,
            direction="outbound",
            content=farewell,
            status="queued",
        )
        db.add(out_msg)
        await db.commit()
        await publish_conversation_event(advertiser.id, {"type": "message", "contact_id": str(contact.id)})

        sid_h, err_h = await send(from_number, farewell)
        if sid_h:
            out_msg.status = "sent"
            out_msg.wa_message_id = sid_h
            out_msg.sent_at = datetime.now(timezone.utc)
        else:
            out_msg.status = "failed"
            out_msg.error_code = err_h
        await db.commit()
        await publish_conversation_event(advertiser.id, {"type": "message", "contact_id": str(contact.id)})

        if advertiser.whatsapp_number or advertiser.phone:
            owner_wa = advertiser.whatsapp_number or advertiser.phone
            try:
                await send_owner(owner_wa, f"🙋 {contact_name} pidió hablar con una persona — revisa el Inbox.")
            except Exception:
                logger.warning("[HANDOFF] Failed to notify owner of client-requested handoff", exc_info=True)
        return {"message": "ok"}

    # Catalog query (channel-agnostic, shared with the widget) — checked
    # first: narrowest, read-only, never creates a row, so it can't collide
    # with the appointment/order state machines below.
    catalog_reply = await handle_catalog_query(db, advertiser, body_text)
    if catalog_reply is not None:
        updated_msgs = conv.messages + [
            {"role": "user", "content": body_text},
            {"role": "assistant", "content": catalog_reply},
        ]
        conv.messages = updated_msgs[-40:]
        conv.last_activity = func.now()

        out_msg = Message(
            advertiser_id=advertiser.id,
            contact_id=contact.id,
            direction="outbound",
            content=catalog_reply,
            status="queued",
        )
        db.add(out_msg)
        await db.commit()
        await publish_conversation_event(advertiser.id, {"type": "message", "contact_id": str(contact.id)})

        sid_c, err_c = await send(from_number, catalog_reply)
        if sid_c:
            out_msg.status = "sent"
            out_msg.wa_message_id = sid_c
            out_msg.sent_at = datetime.now(timezone.utc)
        else:
            out_msg.status = "failed"
            out_msg.error_code = err_c
        await db.commit()
        await publish_conversation_event(advertiser.id, {"type": "message", "contact_id": str(contact.id)})
        return {"message": "ok"}

    # Appointment self-service booking (channel-agnostic, shared with the
    # widget) — checked before the order state machine so "quiero pedir una
    # cita" resolves to booking, not to detect_order_intent's bare "pedir".
    from app.core.redis import get_redis_optional

    _appt_redis = await get_redis_optional()
    appointment_reply = await handle_appointment_booking(db, advertiser, contact, body_text, _appt_redis, channel="whatsapp")
    if appointment_reply is not None:
        updated_msgs = conv.messages + [
            {"role": "user", "content": body_text},
            {"role": "assistant", "content": appointment_reply},
        ]
        conv.messages = updated_msgs[-40:]
        conv.last_activity = func.now()

        out_msg = Message(
            advertiser_id=advertiser.id,
            contact_id=contact.id,
            direction="outbound",
            content=appointment_reply,
            status="queued",
        )
        db.add(out_msg)
        await db.commit()
        await publish_conversation_event(advertiser.id, {"type": "message", "contact_id": str(contact.id)})

        from app.workers.tasks import update_contact_engagement_score

        sid_a, err_a = await send(from_number, appointment_reply)
        if sid_a:
            out_msg.status = "sent"
            out_msg.wa_message_id = sid_a
            out_msg.sent_at = datetime.now(timezone.utc)
        else:
            out_msg.status = "failed"
            out_msg.error_code = err_a
        await db.commit()
        await publish_conversation_event(advertiser.id, {"type": "message", "contact_id": str(contact.id)})
        update_contact_engagement_score.apply_async(
            args=[str(contact.id)],
            queue="whatsapp",
            countdown=10,
        )
        return {"message": "ok"}

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
            pending_order.payment_method = body_text.strip()
            pending_order.state = "confirmed"
            pending_order.confirmed_at = datetime.now(timezone.utc)
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
                owner_number = advertiser.whatsapp_number or advertiser.phone
                await send_owner(owner_number, wa_notify)

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
                pending_order.notes = body_text.strip()
                pending_order.state = "plan_confirmed"
                pending_order.confirmed_at = datetime.now(timezone.utc)
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
                    owner_number = advertiser.whatsapp_number or advertiser.phone
                    await send_owner(owner_number, wa_notify)

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
                owner_number = advertiser.whatsapp_number or advertiser.phone
                try:
                    await send_owner(owner_number, req_notify)
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

                active_products = await get_active_products(db, advertiser.id)
                matched = match_products_in_text(active_products, body_text)
                if matched:
                    db.add_all([
                        OrderItem(
                            order_id=new_order.id,
                            product_id=product.id,
                            product_name_snapshot=product.name,
                            quantity=qty,
                        )
                        for product, qty in matched
                    ])
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
        await publish_conversation_event(advertiser.id, {"type": "message", "contact_id": str(contact.id)})

        from app.workers.tasks import update_contact_engagement_score

        sid_o, err_o = await send(from_number, order_reply)
        if sid_o:
            out_msg.status = "sent"
            out_msg.wa_message_id = sid_o
            out_msg.sent_at = datetime.now(timezone.utc)
        else:
            out_msg.status = "failed"
            out_msg.error_code = err_o
        await db.commit()
        await publish_conversation_event(advertiser.id, {"type": "message", "contact_id": str(contact.id)})
        update_contact_engagement_score.apply_async(
            args=[str(contact.id)],
            queue="whatsapp",
            countdown=10,
        )
        return {"message": "ok"}

    # Build conversation history
    history = conv.messages[-40:] if conv.messages else []
    time_gap_note = format_time_gap_note(previous_last_activity)

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
            time_gap_note=time_gap_note,
        )
    except Exception as e:
        logger.error("[PIPELINE] RAG/Claude error: %s", e, exc_info=True)
        # Escalar en vez de arriesgarse a que el bot siga "adivinando" sin
        # el modelo funcionando — un genérico repetido en cada turno se
        # siente peor que admitir el problema y pasar a un humano.
        biz = advertiser.business_name or "el negocio"
        conv.status = "escalated"
        reply = (
            f"Disculpa, tuve un problema técnico. Ya avisé al equipo de {biz} "
            "para que te atienda directamente en un momento 🙏"
        )
        if advertiser.whatsapp_number or advertiser.phone:
            owner_wa = advertiser.whatsapp_number or advertiser.phone
            try:
                await send_owner(owner_wa, f"⚠️ El bot falló respondiéndole a {contact_name} — revisa el Inbox.")
            except Exception:
                logger.warning("[HANDOFF] Failed to notify owner of bot-error handoff", exc_info=True)

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
    await publish_conversation_event(advertiser.id, {"type": "message", "contact_id": str(contact.id)})

    from app.workers.tasks import (
        auto_tag_contact_from_conversation,
        send_welcome_cuna,
        trigger_automation_for_contact,
        update_contact_engagement_score,
    )

    sid, err = await send(from_number, reply)
    if sid:
        out_msg.status = "sent"
        out_msg.wa_message_id = sid
        out_msg.sent_at = datetime.now(timezone.utc)
    else:
        out_msg.status = "failed"
        out_msg.error_code = err
    await db.commit()
    await publish_conversation_event(advertiser.id, {"type": "message", "contact_id": str(contact.id)})

    try:
        update_contact_engagement_score.apply_async(
            args=[str(contact.id)],
            queue="whatsapp",
            countdown=10,
        )
    except Exception:
        logger.warning("[PIPELINE] Failed to queue engagement score update")

    if _is_new_contact and advertiser.business_name:
        try:
            send_welcome_cuna.apply_async(
                kwargs={
                    "advertiser_id": str(advertiser.id),
                    "to": from_number,
                    "business_name": advertiser.business_name,
                },
                queue="whatsapp",
                countdown=2,
            )
        except Exception:
            logger.warning("[PIPELINE] Failed to queue welcome cuna")
        try:
            trigger_automation_for_contact.apply_async(
                args=[str(contact.id), str(advertiser.id), "new_contact"],
                queue="whatsapp",
                countdown=15,
            )
        except Exception:
            logger.warning("[PIPELINE] Failed to queue automation")
    else:
        try:
            trigger_automation_for_contact.apply_async(
                args=[str(contact.id), str(advertiser.id), "keyword", body_text],
                queue="whatsapp",
                countdown=5,
            )
        except Exception:
            logger.warning("[PIPELINE] Failed to queue automation")

    try:
        auto_tag_contact_from_conversation.apply_async(
            args=[str(contact.id)],
            queue="whatsapp",
            countdown=30,
        )
    except Exception:
        logger.warning("[PIPELINE] Failed to queue auto-tag")

    return {"message": "ok"}
