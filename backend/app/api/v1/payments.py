"""
Payments router — /api/v1/plans, /api/v1/checkout, /api/v1/transactions
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from redis.asyncio import Redis as AsyncRedis
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import stripe as stripe_lib  # type: ignore

from app.api.deps import get_current_user
from app.api.idempotency import idempotent_post, store_idempotency_response
from app.core.redis import get_redis_optional
from app.config import settings
from app.database import get_db
from app.models.transaction import Transaction
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["payments"])


class CheckoutSessionBody(BaseModel):
    plan: str

stripe_lib.api_key = settings.STRIPE_SECRET_KEY

PLANS = {
    "starter":    {"name": "Starter",    "price_mxn": 499,   "price_usd": 29,   "messages": 200,   "days": 30},
    "growth":     {"name": "Growth",     "price_mxn": 999,   "price_usd": 59,   "messages": 500,   "days": 30},
    "pro":        {"name": "Pro",        "price_mxn": 2499,  "price_usd": 149,  "messages": 1000,  "days": 30},
    "business":   {"name": "Business",   "price_mxn": 6799,  "price_usd": 399,  "messages": 3000,  "days": 30},
    "enterprise": {"name": "Enterprise", "price_mxn": 19999, "price_usd": 1199, "messages": 10000, "days": 30},
}

# Fuente de verdad para cuotas de mensajes.
# Importado por webhooks.py para evitar duplicar esta tabla.
PLAN_MESSAGES: dict[str, int] = {key: val["messages"] for key, val in PLANS.items()}


@router.get("/plans")
async def list_plans() -> dict:
    return PLANS


@router.post("/checkout/create-session")
async def create_checkout_session(
    request: Request,
    body: CheckoutSessionBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(idempotent_post),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict:
    plan_key = body.plan
    if plan_key not in PLANS:
        raise HTTPException(status_code=400, detail="Plan inválido")

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Pagos no configurados")

    plan = PLANS[plan_key]

    # Ensure Stripe customer
    if not current_user.stripe_customer_id:
        customer = stripe_lib.Customer.create(
            email=current_user.email,
            metadata={"user_id": str(current_user.id)},
        )
        current_user.stripe_customer_id = customer.id
        await db.commit()

    session = stripe_lib.checkout.Session.create(
        customer=current_user.stripe_customer_id,
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"IaRadio {plan['name']}"},
                    "unit_amount": plan["price_usd"] * 100,
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }
        ],
        mode="subscription",
        success_url=f"{settings.FRONTEND_URL}/app/dashboard?success=1",
        cancel_url=f"{settings.FRONTEND_URL}/app/plans",
        metadata={"plan": plan_key, "user_id": str(current_user.id)},
    )

    logger.info("Checkout session created for user %s, plan %s", current_user.id, plan_key)
    out = {"checkout_url": session.url}
    await store_idempotency_response(request, redis, out)
    return out


@router.post("/cancel-subscription")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cancel the user's active Stripe subscription at period end and release pool number."""
    from app.services.number_pool_service import release_pool_number

    if current_user.subscription_status != "active" or not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No tienes una suscripción activa")

    # Find active Stripe subscription
    subs = stripe_lib.Subscription.list(
        customer=current_user.stripe_customer_id,
        status="active",
        limit=1,
    )
    if not subs.data:
        raise HTTPException(status_code=400, detail="No se encontró suscripción activa en Stripe")

    sub = subs.data[0]
    # Cancel at period end so they keep access for the paid period
    stripe_lib.Subscription.modify(sub.id, cancel_at_period_end=True)

    current_user.cancel_at_period_end = True
    await db.commit()

    logger.info("Subscription cancelled at period end for user %s", current_user.id)
    return {"message": "Suscripción cancelada. Seguirás teniendo acceso hasta el final del período de facturación."}


@router.get("/transactions")
async def list_transactions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> list:
    result = await db.execute(
        select(Transaction)
        .where(Transaction.advertiser_id == current_user.id)
        .order_by(Transaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    txns = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "amount": float(t.amount),
            "currency": t.currency,
            "plan": t.plan,
            "status": t.status,
            "created_at": t.created_at,
        }
        for t in txns
    ]
