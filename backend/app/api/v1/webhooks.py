"""
Webhooks router — /api/v1/webhooks
"""
import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.order import Order
from app.models.appointment import Appointment
from app.models.user import User
from app.services.coupon_service import is_redeem_intent, is_expired
from app.services.number_pool_service import assign_pool_number, release_pool_number
from app.services.rag_service import answer_with_rag
from app.services.claude_service import detect_order_intent
from app.api.v1.payments import PLAN_MESSAGES  # fuente de verdad para cuotas

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _validate_twilio_signature(request_url: str, params: dict, signature: str) -> bool:
    """Validate X-Twilio-Signature HMAC-SHA1."""
    sorted_params = "".join(f"{k}{v}" for k, v in sorted(params.items()))
    s = request_url + sorted_params
    mac = hmac.new(
        settings.TWILIO_AUTH_TOKEN.encode("utf-8"),
        s.encode("utf-8"),
        hashlib.sha1,
    )
    import base64
    expected = base64.b64encode(mac.digest()).decode()
    return hmac.compare_digest(expected, signature)


@router.post("/twilio/incoming")
async def twilio_incoming(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle incoming WhatsApp messages from Twilio."""
    signature = request.headers.get("X-Twilio-Signature", "")
    form_data = dict(await request.form())

    if settings.TWILIO_AUTH_TOKEN:
        url = str(request.url)
        if not _validate_twilio_signature(url, form_data, signature):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Firma Twilio inválida")

    from_number = form_data.get("From", "").replace("whatsapp:", "")
    to_number = form_data.get("To", "").replace("whatsapp:", "")
    body_text = form_data.get("Body", "").strip()

    # Handle WhatsApp media attachments (images, audio, documents)
    num_media = int(form_data.get("NumMedia", "0"))
    if num_media > 0 and not body_text:
        media_url = form_data.get("MediaUrl0", "")
        media_type = form_data.get("MediaContentType0", "")
        if media_url:
            body_text = f"[media:{media_type}]{media_url}"

    # Find advertiser by whatsapp_number
    result = await db.execute(
        select(User).where(User.whatsapp_number == to_number)
    )
    advertiser = result.scalar_one_or_none()

    # Fallback: shared IaRadio number — can't route to a specific advertiser on inbound.
    # Shared number is outbound-only (campaigns). Inbound bot requires a dedicated number.
    if not advertiser:
        shared = settings.TWILIO_WHATSAPP_NUMBER.lstrip("+")
        to_clean = to_number.lstrip("+")
        if to_clean == shared:
            # Shared number: acknowledge without bot response
            return {"message": "ok"}
        return {"message": "ok"}

    # Auto-unsubscribe on STOP words
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
            await db.commit()
        return {"message": "ok"}

    # ─── APPOINTMENT CONFIRMATION HANDLER ───────────────────────────────────
    # Detecta respuestas 1/2 de contactos que tienen cita esperando confirmación
    _appt_reply: str | None = None
    confirm_keywords = {"1", "si", "sí", "yes", "confirmo", "confirmar", "✅", "ok", "dale"}
    cancel_keywords  = {"2", "no", "cancela", "cancelar", "cancelar cita", "no puedo", "❌"}
    normalized = body_text.lower().strip()

    if normalized in confirm_keywords or normalized in cancel_keywords:
        # Look for an appointment awaiting confirmation from this phone
        appt_result = await db.execute(
            select(Appointment).where(
                Appointment.advertiser_id == advertiser.id,
                Appointment.awaiting_confirmation == True,  # noqa: E712
                Appointment.status.in_(["pending", "confirmed"]),
            ).order_by(Appointment.scheduled_at.asc())
        )
        pending_appt = appt_result.scalars().first()

        if pending_appt:
            from datetime import datetime, timezone as _tz
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
                # Notify business owner
                owner_notify = (
                    f"✅ *Cita confirmada por el cliente*\n"
                    f"👤 {pending_appt.customer_name} ({from_number})\n"
                    f"📌 {pending_appt.service}\n"
                    f"🕐 {fecha} a las {hora}"
                )
            else:  # cancel
                pending_appt.status = "cancelled"
                pending_appt.awaiting_confirmation = False
                _appt_reply = (
                    f"❌ Cita cancelada.\n\n"
                    f"Sin problema, {pending_appt.customer_name.split()[0]}. "
                    f"Escríbenos cuando quieras reagendar y te buscamos un nuevo horario 📅"
                )
                owner_notify = (
                    f"❌ *Cita CANCELADA por el cliente*\n"
                    f"👤 {pending_appt.customer_name} ({from_number})\n"
                    f"📌 {pending_appt.service}\n"
                    f"🕐 {fecha} a las {hora}"
                )

            await db.commit()

            # Send reply to client
            await _send_wa(from_number, _appt_reply, from_number=from_wa)

            # Notify owner
            if advertiser.whatsapp_number or advertiser.phone:
                owner_wa = advertiser.whatsapp_number or advertiser.phone
                await _send_wa(owner_wa, owner_notify)

            return {"message": "ok"}
    # ─── END APPOINTMENT CONFIRMATION ────────────────────────────────────────

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
            # Find an active coupon for this contact
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

                # Increment campaign's coupons_redeemed counter
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
            from app.workers.tasks import send_whatsapp_message
            send_whatsapp_message.apply_async(
                args=[str(out_msg.id), from_number, redeem_reply],
                countdown=2,
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

    # Save inbound message
    msg = Message(
        advertiser_id=advertiser.id,
        contact_id=contact.id,
        direction="inbound",
        content=body_text,
        status="delivered",
    )
    db.add(msg)

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
        )
        db.add(conv)
        await db.flush()

    # ─── ORDER STATE MACHINE ──────────────────────────────────────────────
    # Check if there's a pending order in progress for this contact
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
        # Continue collecting order data based on current state
        if pending_order.state == "collecting_name":
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

            # ── Notify owner via WhatsApp ─────────────────────────────────
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

            # ── Notify owner via email ────────────────────────────────────
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
        # No pending order — detect if this message is an order intent
        is_order = await detect_order_intent(body_text)
        if is_order:
            # Get next order number for this advertiser
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
                state="collecting_name",
                order_number=order_count + 1,
            )
            db.add(new_order)
            await db.flush()

            order_reply = (
                "¡Con gusto te ayudo con tu pedido! 🛒\n"
                "Para completarlo, ¿a qué nombre va el pedido?"
            )

    # If we handled an order step, send that reply and skip RAG
    if order_reply is not None:
        updated_msgs = conv.messages + [
            {"role": "user", "content": body_text},
            {"role": "assistant", "content": order_reply},
        ]
        conv.messages = updated_msgs[-40:]

        out_msg = Message(
            advertiser_id=advertiser.id,
            contact_id=contact.id,
            direction="outbound",
            content=order_reply,
            status="queued",
        )
        db.add(out_msg)
        await db.commit()

        from app.workers.tasks import send_whatsapp_message
        send_whatsapp_message.apply_async(
            args=[str(out_msg.id), from_number, order_reply],
            queue="whatsapp",
            countdown=2,
        )
        return {"message": "ok"}
    # ─── END ORDER STATE MACHINE ──────────────────────────────────────────

    # Build conversation history (last 20 turns)
    history = conv.messages[-40:] if conv.messages else []

    # Generate RAG response
    reply = await answer_with_rag(
        advertiser_id=str(advertiser.id),
        query=body_text,
        conversation_history=history,
        db=db,
        business_name=advertiser.business_name or "el negocio",
        bot_name=advertiser.bot_name or "Asistente",
        bot_personality=advertiser.bot_personality or "amigable y profesional",
    )

    # Update conversation history
    updated_msgs = conv.messages + [
        {"role": "user", "content": body_text},
        {"role": "assistant", "content": reply},
    ]
    conv.messages = updated_msgs[-40:]  # keep last 20 turns

    # Save outbound message record
    out_msg = Message(
        advertiser_id=advertiser.id,
        contact_id=contact.id,
        direction="outbound",
        content=reply,
        status="queued",
    )
    db.add(out_msg)
    await db.commit()

    # Send reply via Twilio (async, humanized delay)
    from app.workers.tasks import send_whatsapp_message, send_welcome_cuna
    send_whatsapp_message.apply_async(
        args=[str(out_msg.id), from_number, reply],
        queue="whatsapp",
        countdown=__import__("random").randint(1, 5),
    )

    # New lead: automatically send a radio cuña ~10 seconds after the text reply
    # This feels natural — like a radio ad that plays right after the greeting
    if _is_new_contact and advertiser.business_name:
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

    return {"message": "ok"}


@router.post("/twilio/status")
async def twilio_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update message delivery status from Twilio callbacks."""
    form_data = dict(await request.form())
    twilio_sid = form_data.get("MessageSid")
    msg_status = form_data.get("MessageStatus")

    if twilio_sid and msg_status:
        result = await db.execute(
            select(Message).where(Message.twilio_sid == twilio_sid)
        )
        msg = result.scalar_one_or_none()
        if msg:
            from datetime import datetime, timezone
            status_map = {
                "sent": "sent",
                "delivered": "delivered",
                "read": "read",
                "failed": "failed",
                "undelivered": "failed",
            }
            new_status = status_map.get(msg_status, msg.status)
            old_status = msg.status
            msg.status = new_status

            # Stamp delivery/read timestamps
            now = datetime.now(timezone.utc)
            if new_status == "delivered" and not msg.delivered_at:
                msg.delivered_at = now
            elif new_status == "read" and not msg.read_at:
                msg.read_at = now

            # Update campaign aggregate stats
            if msg.campaign_id and new_status != old_status:
                camp_result = await db.execute(
                    select(Campaign).where(Campaign.id == msg.campaign_id)
                )
                campaign = camp_result.scalar_one_or_none()
                if campaign:
                    stats = dict(campaign.stats)
                    if new_status == "sent":
                        stats["sent"] = stats.get("sent", 0) + 1
                    elif new_status == "delivered":
                        stats["delivered"] = stats.get("delivered", 0) + 1
                    elif new_status == "read":
                        stats["read"] = stats.get("read", 0) + 1
                    elif new_status == "failed":
                        stats["failed"] = stats.get("failed", 0) + 1
                    campaign.stats = stats

            await db.commit()

    return {"message": "ok"}


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhook events."""
    import stripe as stripe_lib  # type: ignore

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_lib.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe_lib.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Firma Stripe inválida")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        from datetime import datetime, timezone, timedelta
        from app.models.transaction import Transaction

        customer_id = data.get("customer")
        plan = data.get("metadata", {}).get("plan")
        amount_total = data.get("amount_total", 0)  # cents
        currency = data.get("currency", "usd")

        result = await db.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
        user = result.scalar_one_or_none()
        if user and plan:
            plan_days = 30
            user.subscription_status = "active"
            user.current_plan = plan
            user.messages_remaining = PLAN_MESSAGES.get(plan, 0)
            user.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=plan_days)

            # Auto-assign a dedicated pool number for any paid plan
            if user.whatsapp_number_source == "shared":
                await assign_pool_number(user, db)

            # Record transaction
            txn = Transaction(
                advertiser_id=user.id,
                stripe_payment_id=data.get("payment_intent") or data.get("id"),
                amount=amount_total / 100,
                currency=currency.upper(),
                plan=plan,
                status="succeeded",
            )
            db.add(txn)
            await db.commit()

    elif event_type == "invoice.payment_succeeded":
        # Recurring payment — renew plan
        from datetime import datetime, timezone, timedelta
        from app.models.transaction import Transaction

        customer_id = data.get("customer")
        result = await db.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
        user = result.scalar_one_or_none()
        if user and user.current_plan:
            user.messages_remaining = PLAN_MESSAGES.get(user.current_plan, 0)
            user.subscription_status = "active"
            user.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=30)

            txn = Transaction(
                advertiser_id=user.id,
                stripe_payment_id=data.get("payment_intent"),
                amount=data.get("amount_paid", 0) / 100,
                currency=data.get("currency", "usd").upper(),
                plan=user.current_plan,
                status="succeeded",
            )
            db.add(txn)
            await db.commit()

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        result = await db.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.subscription_status = "churned"
            user.messages_remaining = 0
            await release_pool_number(user, db)  # return number to pool
            await db.commit()

    return {"received": True}
