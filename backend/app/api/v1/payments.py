"""
Payments router — /api/v1/plans, /api/v1/checkout, /api/v1/transactions
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import stripe as stripe_lib  # type: ignore

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.transaction import Transaction
from app.models.user import User

router = APIRouter(tags=["payments"])

stripe_lib.api_key = settings.STRIPE_SECRET_KEY

PLANS = {
    "starter": {"name": "Starter", "price_mxn": 499, "price_usd": 29, "messages": 200, "days": 30},
    "growth": {"name": "Growth", "price_mxn": 999, "price_usd": 59, "messages": 500, "days": 30},
    "pro": {"name": "Pro", "price_mxn": 2499, "price_usd": 149, "messages": 1000, "days": 30},
    "business": {"name": "Business", "price_mxn": 6799, "price_usd": 399, "messages": 3000, "days": 30},
    "enterprise": {"name": "Enterprise", "price_mxn": 19999, "price_usd": 1199, "messages": 10000, "days": 30},
}


@router.get("/plans")
async def list_plans():
    return PLANS


@router.post("/checkout/create-session")
async def create_checkout_session(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan_key = body.get("plan")
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
        success_url=f"{settings.FRONTEND_URL}/dashboard?success=1",
        cancel_url=f"{settings.FRONTEND_URL}/plans",
        metadata={"plan": plan_key, "user_id": str(current_user.id)},
    )

    return {"checkout_url": session.url}


@router.get("/transactions")
async def list_transactions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Transaction)
        .where(Transaction.advertiser_id == current_user.id)
        .order_by(Transaction.created_at.desc())
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
