"""
Stripe webhook handler — subscription and payment events.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.number_pool_service import assign_pool_number, release_pool_number
from app.api.v1.payments import PLAN_MESSAGES

logger = logging.getLogger(__name__)


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
        amount_total = data.get("amount_total", 0)
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

            if user.whatsapp_number_source == "shared":
                await assign_pool_number(user, db)

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

    elif event_type == "customer.subscription.updated":
        customer_id = data.get("customer")
        status = data.get("status")
        result = await db.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
        user = result.scalar_one_or_none()
        if user and status in ("past_due", "incomplete", "unpaid", "canceled"):
            user.subscription_status = "suspended" if status in ("past_due", "unpaid") else "churned"
            user.messages_remaining = 0
            await release_pool_number(user, db)
            await db.commit()
            logger.info(
                "[WEBHOOK] Subscription %s for user %s — status=%s, pool released",
                event_type, customer_id, status,
            )

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        result = await db.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.subscription_status = "churned"
            user.messages_remaining = 0
            await release_pool_number(user, db)
            await db.commit()

    return {"received": True}
