"""
Payments router — /api/v1/plans, /api/v1/checkout, /api/v1/transactions
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from redis.asyncio import Redis as AsyncRedis
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

import stripe as stripe_lib  # type: ignore

from app.api.deps import get_current_user
from app.api.idempotency import idempotent_post, store_idempotency_response
from app.core.redis import get_redis_optional
from app.config import settings
from app.database import get_db
from app.models.founder_program import FounderProgram
from app.models.transaction import Transaction
from app.models.user import User
from app.services.analytics_service import capture_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["payments"])


class CheckoutSessionBody(BaseModel):
    plan: str
    founder: bool = False
    billing_cycle: str = "monthly"  # "monthly" | "annual"

stripe_lib.api_key = settings.STRIPE_SECRET_KEY

PLANS = {
    "micro":      {"name": "Micro",      "price_mxn": 299,   "price_usd": 18,   "messages": 100,   "days": 30},
    "starter":    {"name": "Starter",    "price_mxn": 499,   "price_usd": 29,   "messages": 200,   "days": 30},
    "growth":     {"name": "Growth",     "price_mxn": 999,   "price_usd": 59,   "messages": 500,   "days": 30},
    "pro":        {"name": "Pro",        "price_mxn": 2499,  "price_usd": 149,  "messages": 1000,  "days": 30},
    "business":   {"name": "Business",   "price_mxn": 6799,  "price_usd": 399,  "messages": 3000,  "days": 30},
    "enterprise": {"name": "Enterprise", "price_mxn": 19999, "price_usd": 1199, "messages": 10000, "days": 30},
}

# Programa "Fundadores" — precio bloqueado por 12 meses para los primeros
# FOUNDER_SLOTS_TOTAL clientes (ver migración 0048), solo en Starter/Growth.
# No es un "antes/ahora" inventado (ver auditoría de precios) — es un precio
# real y honesto, distinto del de lista, con cupo limitado real en la DB.
FOUNDER_PRICES = {
    "starter": {"price_mxn": 349, "price_usd": 21},
    "growth":  {"price_mxn": 699, "price_usd": 41},
}

# Fuente de verdad para cuotas de mensajes.
# Importado por webhooks.py para evitar duplicar esta tabla.
PLAN_MESSAGES: dict[str, int] = {key: val["messages"] for key, val in PLANS.items()}


@router.get("/plans")
async def list_plans() -> dict:
    return PLANS


@router.get("/founder-status")
async def founder_status(db: AsyncSession = Depends(get_db)) -> dict:
    """Cupos restantes del programa Fundadores — público, sin auth, para
    mostrar disponibilidad real (no inflada) en la página de precios."""
    result = await db.execute(select(FounderProgram).limit(1))
    program = result.scalar_one_or_none()
    if not program:
        return {"available": False, "slots_left": 0, "slots_total": 0, "prices": FOUNDER_PRICES}
    slots_left = max(program.slots_total - program.slots_used, 0)
    return {
        "available": slots_left > 0,
        "slots_left": slots_left,
        "slots_total": program.slots_total,
        "prices": FOUNDER_PRICES,
    }


async def _claim_founder_slot(db: AsyncSession) -> bool:
    """Reclama un cupo de fundador de forma atómica — un solo UPDATE
    condicionado evita que dos checkouts simultáneos vendan el mismo cupo
    (sin necesitar un lock explícito ni una transacción con SELECT FOR UPDATE)."""
    result = await db.execute(
        update(FounderProgram)
        .where(FounderProgram.slots_used < FounderProgram.slots_total)
        .values(slots_used=FounderProgram.slots_used + 1)
        .returning(FounderProgram.slots_used)
    )
    claimed = result.first() is not None
    await db.commit()
    return claimed


@router.post("/checkout/create-session")
async def create_checkout_session(
    request: Request,
    body: CheckoutSessionBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(idempotent_post),
    redis: AsyncRedis | None = Depends(get_redis_optional),
    _founder_slot_claimed: bool = False,
) -> dict:
    try:
        plan_key = body.plan
        if plan_key not in PLANS:
            raise HTTPException(status_code=400, detail="Plan inválido")

        if body.billing_cycle not in ("monthly", "annual"):
            raise HTTPException(status_code=400, detail="billing_cycle inválido")

        if body.founder and body.billing_cycle == "annual":
            raise HTTPException(status_code=400, detail="El programa Fundadores no aplica a pago anual")

        if not settings.STRIPE_SECRET_KEY:
            raise HTTPException(status_code=503, detail="Pagos no configurados")

        plan = PLANS[plan_key]
        interval = "month"
        price_usd = plan["price_usd"]

        if body.founder:
            if plan_key not in FOUNDER_PRICES:
                raise HTTPException(status_code=400, detail="El programa Fundadores solo aplica a Starter y Growth")
            # No reclamar dos veces si esto es un reintento tras "No such customer"
            # (ver except InvalidRequestError abajo) — ya se reclamó en el intento original.
            if not _founder_slot_claimed and not await _claim_founder_slot(db):
                raise HTTPException(status_code=409, detail="Ya no quedan lugares del programa Fundadores")
            price_usd = FOUNDER_PRICES[plan_key]["price_usd"]
        elif body.billing_cycle == "annual":
            interval = "year"
            price_usd = plan["price_usd"] * 10  # 12 meses al precio de 10 — 2 meses gratis

        customer_id = await _resolve_stripe_customer(current_user, db)
        session = stripe_lib.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": f"IaRadio {plan['name']}"},
                        "unit_amount": price_usd * 100,
                        "recurring": {"interval": interval},
                    },
                    "quantity": 1,
                }
            ],
            mode="subscription",
            success_url=f"{settings.FRONTEND_URL}/app/dashboard?success=1",
            cancel_url=f"{settings.FRONTEND_URL}/app/plans",
            metadata={
                "plan": plan_key,
                "user_id": str(current_user.id),
                "founder": "true" if body.founder else "false",
                "billing_cycle": body.billing_cycle,
            },
        )

        logger.info("Checkout session created for user %s, plan %s", current_user.id, plan_key)
        capture_event("checkout_created", user_id=current_user.id, properties={"plan": plan_key, "founder": body.founder, "billing_cycle": body.billing_cycle})
        out = {"checkout_url": session.url}
        await store_idempotency_response(request, redis, out)
        return out

    except HTTPException:
        raise
    except stripe_lib.error.InvalidRequestError as e:
        if "No such customer" in str(e):
            current_user.stripe_customer_id = None
            await db.commit()
            return await create_checkout_session(
                request, body, current_user, db, _, redis,
                _founder_slot_claimed=body.founder,
            )
        logger.exception("Stripe InvalidRequestError: %s", e)
        raise HTTPException(status_code=502, detail="Error de comunicación con Stripe")
    except stripe_lib.error.AuthenticationError:
        logger.exception("Stripe AuthenticationError — revisa STRIPE_SECRET_KEY")
        raise HTTPException(status_code=502, detail="Error de autenticación con Stripe")
    except stripe_lib.error.StripeError as e:
        logger.exception("Stripe error inesperado: %s", e)
        raise HTTPException(status_code=502, detail="Error al procesar el pago. Stripe puede no estar activado para cobros en vivo.")
    except Exception as e:
        logger.exception("Error inesperado en create_checkout_session (tipo=%s): %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail=f"Error interno al crear sesión de pago: {type(e).__name__}")


async def _resolve_stripe_customer(user: User, db: AsyncSession) -> str:
    if user.stripe_customer_id:
        try:
            stripe_lib.Customer.retrieve(user.stripe_customer_id)
            return user.stripe_customer_id
        except stripe_lib.error.InvalidRequestError:
            logger.warning("Stripe customer %s no existe (test→live?), creando uno nuevo", user.stripe_customer_id)
            user.stripe_customer_id = None
            await db.commit()
    customer = stripe_lib.Customer.create(
        email=user.email,
        metadata={"user_id": str(user.id)},
    )
    user.stripe_customer_id = customer.id
    await db.commit()
    return customer.id


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
