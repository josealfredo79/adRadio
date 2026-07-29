"""
Stripe webhook handler — subscription and payment events.
"""
import logging
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.transaction import Transaction
from app.models.user import User
from app.services.analytics_service import capture_event
from app.api.v1.payments import PLAN_MESSAGES, PLANS
from app.core.rate_limiter import limiter

logger = logging.getLogger(__name__)


async def _lookup_user(customer_id: str | None, db: AsyncSession) -> User | None:
    if not customer_id:
        return None
    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    return result.scalar_one_or_none()


async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Handle Stripe webhook events."""
    import stripe as stripe_lib  # type: ignore

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("[WEBHOOK] STRIPE_WEBHOOK_SECRET is not configured")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    try:
        event = stripe_lib.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        logger.warning("[WEBHOOK] Invalid payload")
        raise HTTPException(status_code=400, detail="Payload inválido")
    except stripe_lib.error.SignatureVerificationError:
        logger.warning("[WEBHOOK] Invalid signature")
        raise HTTPException(status_code=400, detail="Firma Stripe inválida")

    event_id = event.get("id", "unknown")
    event_type = event["type"]
    data = event["data"]["object"]
    customer_id = data.get("customer")

    logger.info("[WEBHOOK] event=%s id=%s customer=%s", event_type, event_id, customer_id)

    if event_type == "checkout.session.completed":
        plan = data.get("metadata", {}).get("plan")
        amount_total = data.get("amount_total", 0)
        currency = data.get("currency", "usd")
        payment_intent = data.get("payment_intent") or data.get("id")
        if not payment_intent:
            logger.warning("[WEBHOOK] checkout.session.completed missing payment_intent")
            return {"received": True}

        # Idempotency — skip if already processed
        existing = await db.execute(
            select(Transaction).where(
                Transaction.stripe_payment_id == payment_intent
            )
        )
        if existing.scalar_one_or_none():
            logger.info("[WEBHOOK] Duplicate checkout event %s, skipped", payment_intent)
            return {"received": True}

        user = await _lookup_user(customer_id, db)
        if user and plan:
            plan_days = PLANS.get(plan, {}).get("days", 30)
            user.subscription_status = "active"
            user.current_plan = plan
            user.cancel_at_period_end = False
            user.messages_remaining = (user.messages_remaining or 0) + PLAN_MESSAGES.get(plan, 0)
            user.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=plan_days)

            txn = Transaction(
                advertiser_id=user.id,
                stripe_payment_id=payment_intent,
                amount=amount_total / 100,
                currency=currency.upper(),
                plan=plan,
                status="succeeded",
            )
            db.add(txn)
            await db.commit()
            logger.info("[WEBHOOK] Checkout completed for user %s, plan %s", user.id, plan)
            capture_event("subscription_started", user_id=user.id, properties={"plan": plan, "amount": amount_total / 100})

    elif event_type == "invoice.payment_succeeded":

        payment_intent = data.get("payment_intent")
        if not payment_intent:
            logger.warning("[WEBHOOK] invoice.payment_succeeded missing payment_intent")
            return {"received": True}

        # Idempotency
        existing = await db.execute(
            select(Transaction).where(
                Transaction.stripe_payment_id == payment_intent
            )
        )
        if existing.scalar_one_or_none():
            logger.info("[WEBHOOK] Duplicate invoice event %s, skipped", payment_intent)
            return {"received": True}

        user = await _lookup_user(customer_id, db)
        if user and user.current_plan:
            plan_days = PLANS.get(user.current_plan, {}).get("days", 30)
            user.messages_remaining = (user.messages_remaining or 0) + PLAN_MESSAGES.get(user.current_plan, 0)
            user.subscription_status = "active"
            user.cancel_at_period_end = False
            user.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=plan_days)

            txn = Transaction(
                advertiser_id=user.id,
                stripe_payment_id=payment_intent,
                amount=data.get("amount_paid", 0) / 100,
                currency=data.get("currency", "usd").upper(),
                plan=user.current_plan,
                invoice_pdf_url=data.get("invoice_pdf"),
                status="succeeded",
            )
            db.add(txn)
            await db.commit()
            logger.info("[WEBHOOK] Invoice paid for user %s, plan %s", user.id, user.current_plan)
            capture_event("invoice_paid", user_id=user.id, properties={"plan": user.current_plan})

    elif event_type == "invoice.payment_failed":

        payment_intent = data.get("payment_intent")
        user = await _lookup_user(customer_id, db)
        if user and payment_intent:
            # Idempotency
            existing = await db.execute(
                select(Transaction).where(
                    Transaction.stripe_payment_id == payment_intent
                )
            )
            if existing.scalar_one_or_none():
                logger.info("[WEBHOOK] Duplicate payment_failed event %s, skipped", payment_intent)
                return {"received": True}

            amount = data.get("amount_due", 0) / 100
            currency = data.get("currency", "usd").upper()

            txn = Transaction(
                advertiser_id=user.id,
                stripe_payment_id=payment_intent,
                amount=amount,
                currency=currency,
                plan=user.current_plan,
                status="failed",
            )
            db.add(txn)
            await db.commit()
            logger.warning(
                "[WEBHOOK] Payment failed for user %s, amount=%s %s",
                user.id, amount, currency,
            )

    elif event_type == "customer.subscription.updated":
        status = data.get("status")
        subscription_id = data.get("id", "unknown")
        user = await _lookup_user(customer_id, db)
        if not user:
            return {"received": True}

        # Idempotency — skip if no meaningful change
        cancel = data.get("cancel_at_period_end", False)
        target_status = None
        if status == "active":
            target_status = "active"
        elif status in ("past_due", "incomplete", "unpaid"):
            target_status = "suspended"
        elif status == "canceled":
            target_status = "churned"

        status_unchanged = (
            target_status and
            user.subscription_status == target_status and
            user.cancel_at_period_end == cancel
        )
        if status_unchanged:
            logger.info(
                "[WEBHOOK] Duplicate subscription.updated event %s skipped (already %s)",
                event_id, target_status,
            )
            return {"received": True}

        changed = False

        # Sync cancel_at_period_end from Stripe
        if cancel != user.cancel_at_period_end:
            user.cancel_at_period_end = cancel
            changed = True
            logger.info("[WEBHOOK] Synced cancel_at_period_end=%s for user %s", cancel, user.id)

        if status == "active":
            if user.subscription_status == "suspended":
                user.subscription_status = "active"
                user.messages_remaining = max(user.messages_remaining or 0, 1)
                changed = True
                logger.info("[WEBHOOK] Subscription reactivated for user %s", user.id)
        elif status in ("past_due", "incomplete", "unpaid"):
            user.subscription_status = "suspended"
            user.messages_remaining = 0
            await db.commit()
            logger.warning(
                "[WEBHOOK] Subscription adverse for user %s — status=%s",
                user.id, status,
            )
        elif status == "canceled":
            user.subscription_status = "churned"
            user.messages_remaining = 0
            user.cancel_at_period_end = False
            await db.commit()
            logger.info("[WEBHOOK] Subscription canceled for user %s", user.id)
            capture_event("subscription_cancelled", user_id=user.id)

        if changed and status == "active":
            await db.commit()

    elif event_type == "customer.subscription.deleted":
        user = await _lookup_user(customer_id, db)
        if not user:
            return {"received": True}
        if user.subscription_status == "churned":
            logger.info("[WEBHOOK] Duplicate subscription.deleted event %s skipped", event_id)
            return {"received": True}
        user.subscription_status = "churned"
        user.messages_remaining = 0
        user.cancel_at_period_end = False
        await release_pool_number(user, db)
        await db.commit()
        logger.info("[WEBHOOK] Subscription deleted for user %s", user.id)

    elif event_type in ("charge.refunded", "charge.dispute.created"):

        payment_intent = data.get("payment_intent")
        if payment_intent:
            result = await db.execute(
                select(Transaction).where(
                    Transaction.stripe_payment_id == payment_intent
                )
            )
            txn = result.scalar_one_or_none()
            if txn:
                txn.status = "refunded" if event_type == "charge.refunded" else "refunded"
                await db.commit()
                logger.info("[WEBHOOK] Transaction %s updated to refunded", payment_intent)

    return {"received": True}


# Rate-limited route wrapper (tests call stripe_webhook directly)
@limiter.limit("20/minute")
async def stripe_webhook_route(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Rate-limited wrapper for stripe_webhook."""
    return await stripe_webhook(request, db)
