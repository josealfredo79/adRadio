"""
Webhooks router — /api/v1/webhooks
"""
import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.user import User
from app.services.coupon_service import is_redeem_intent, is_expired
from app.services.rag_service import answer_with_rag

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

    # Find advertiser by whatsapp_number
    result = await db.execute(
        select(User).where(User.whatsapp_number == to_number)
    )
    advertiser = result.scalar_one_or_none()

    # Fallback: shared AdRadio number — can't route to a specific advertiser on inbound.
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
    from app.workers.tasks import send_whatsapp_message
    send_whatsapp_message.apply_async(
        args=[str(out_msg.id), from_number, reply],
        countdown=__import__("random").randint(1, 5),
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
            plan_messages = {"starter": 200, "pro": 1000, "business": 3000, "enterprise": 10000}
            plan_days = 30
            user.subscription_status = "active"
            user.current_plan = plan
            user.messages_remaining = plan_messages.get(plan, 0)
            user.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=plan_days)

            # Auto-assign a dedicated number from the pool for Pro+ plans
            if plan in ("pro", "business") and user.whatsapp_number_source == "shared":
                pool = settings.twilio_number_pool_list
                if pool:
                    taken_result = await db.execute(
                        select(User.whatsapp_number).where(
                            User.whatsapp_number_source == "pool",
                            User.whatsapp_number.isnot(None),
                        )
                    )
                    taken = {row[0] for row in taken_result.all()}
                    available = [n for n in pool if n not in taken]
                    if available:
                        user.whatsapp_number = available[0]
                        user.whatsapp_number_source = "pool"

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
            plan_messages = {"starter": 200, "pro": 1000, "business": 3000, "enterprise": 10000}
            user.messages_remaining = plan_messages.get(user.current_plan, 0)
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
            await db.commit()

    return {"received": True}
