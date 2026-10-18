"""
Admin endpoints for subscription management.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.api.v1.payments import PLANS
from app.core.redis import get_redis_optional
from app.database import get_db
from app.models.transaction import Transaction
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_admin)])


class SubscriptionUpdateRequest(BaseModel):
    subscription_status: str | None = None
    current_plan: str | None = None
    messages_remaining: int | None = None
    plan_expires_at: datetime | None = None
    cancel_at_period_end: bool | None = None
    stripe_customer_id: str | None = None


class TransactionResponse(BaseModel):
    id: str
    amount: float
    currency: str
    plan: str | None
    status: str
    invoice_pdf_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v)


class UserSubscriptionResponse(BaseModel):
    id: str
    email: str
    business_name: str | None
    subscription_status: str
    current_plan: str
    messages_remaining: int
    plan_expires_at: datetime | None
    cancel_at_period_end: bool
    stripe_customer_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v)


@router.get("/admin/subscriptions")
async def list_subscriptions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    """List all users with subscription info (admin only)."""
    query = select(User)
    if status_filter:
        query = query.where(User.subscription_status == status_filter)
    query = query.order_by(desc(User.created_at))
    total_result = await db.execute(select(func.count(User.id)))
    total = total_result.scalar() or 0
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    result = await db.execute(query)
    users = result.scalars().all()
    return {
        "users": [UserSubscriptionResponse.model_validate(u) for u in users],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/admin/subscriptions/{user_id}")
async def get_subscription(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single user's subscription details (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return UserSubscriptionResponse.model_validate(user)


@router.patch("/admin/subscriptions/{user_id}")
async def update_subscription(
    user_id: str,
    body: SubscriptionUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Manually update a user's subscription (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    fields = body.model_dump(exclude_none=True)
    for key, value in fields.items():
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    logger.info("[ADMIN] Subscription updated for user %s: %s", user_id, fields)
    return UserSubscriptionResponse.model_validate(user)


@router.get("/admin/subscriptions/{user_id}/transactions")
async def list_user_transactions(
    user_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List all transactions for a specific user (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    query = (
        select(Transaction)
        .where(Transaction.advertiser_id == user_id)
        .order_by(desc(Transaction.created_at))
    )
    total_query = select(func.count(Transaction.id)).where(
        Transaction.advertiser_id == user_id
    )
    total_result = await db.execute(total_query)
    total = total_result.scalar() or 0
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    txn_result = await db.execute(query)
    txns = txn_result.scalars().all()
    return {
        "transactions": [TransactionResponse.model_validate(t) for t in txns],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


# ─── Platform stats ─────────────────────────────────────────────────────────


@router.get("/admin/stats")
async def platform_stats(db: AsyncSession = Depends(get_db)):
    """Global platform KPIs (admin only)."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # User counts by subscription status
    status_counts = {}
    for st in ("trial", "active", "suspended", "churned"):
        result = await db.execute(
            select(func.count(User.id)).where(User.subscription_status == st)
        )
        status_counts[st] = result.scalar() or 0

    total_users = sum(status_counts.values())

    # MRR
    mrr_mxn = 0.0
    mrr_usd = 0.0
    stripe_connected = 0
    for plan_key, plan_info in PLANS.items():
        result = await db.execute(
            select(func.count(User.id)).where(
                User.current_plan == plan_key,
                User.subscription_status == "active",
            )
        )
        count = result.scalar() or 0
        mrr_mxn += count * plan_info["price_mxn"]
        mrr_usd += count * plan_info["price_usd"]

    # Stripe connected
    result = await db.execute(
        select(func.count(User.id)).where(User.stripe_customer_id.isnot(None))
    )
    stripe_connected = result.scalar() or 0

    # New users this month
    result = await db.execute(
        select(func.count(User.id)).where(User.created_at >= month_start)
    )
    new_users_month = result.scalar() or 0

    # Messages sent this month (from messages table)
    from app.models.message import Message
    result = await db.execute(
        select(func.count(Message.id)).where(
            Message.direction == "outbound",
            Message.created_at >= month_start,
        )
    )
    messages_month = result.scalar() or 0

    # Messages sent today
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(Message.id)).where(
            Message.direction == "outbound",
            Message.created_at >= day_start,
        )
    )
    messages_today = result.scalar() or 0

    return {
        "total_users": total_users,
        "users_trial": status_counts.get("trial", 0),
        "users_active": status_counts.get("active", 0),
        "users_suspended": status_counts.get("suspended", 0),
        "users_churned": status_counts.get("churned", 0),
        "mrr_mxn": mrr_mxn,
        "mrr_usd": mrr_usd,
        "messages_sent_today": messages_today,
        "messages_sent_month": messages_month,
        "new_users_this_month": new_users_month,
        "stripe_connected": stripe_connected,
    }


# ─── User management ────────────────────────────────────────────────────────


class AdminUserResponse(BaseModel):
    id: str
    email: str
    role: str
    business_name: str | None
    business_category: str | None
    city: str | None
    phone: str | None
    whatsapp_number: str | None
    meta_connection_status: str
    subscription_status: str
    current_plan: str
    messages_remaining: int
    plan_expires_at: datetime | None
    stripe_customer_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v)


@router.get("/admin/users")
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    plan_filter: str | None = Query(None, alias="plan"),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List all users with full info (admin only)."""
    query = select(User)
    if status_filter:
        query = query.where(User.subscription_status == status_filter)
    if plan_filter:
        query = query.where(User.current_plan == plan_filter)
    if search:
        like = f"%{search}%"
        query = query.where(
            (User.email.ilike(like)) | (User.business_name.ilike(like))
        )
    query = query.order_by(desc(User.created_at))

    # Total count with same filters
    count_query = select(func.count(User.id))
    if status_filter:
        count_query = count_query.where(User.subscription_status == status_filter)
    if plan_filter:
        count_query = count_query.where(User.current_plan == plan_filter)
    if search:
        like = f"%{search}%"
        count_query = count_query.where(
            (User.email.ilike(like)) | (User.business_name.ilike(like))
        )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)
    result = await db.execute(query)
    users = result.scalars().all()
    return {
        "users": [AdminUserResponse.model_validate(u) for u in users],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/admin/ab/mascot")
async def mascot_ab_results(redis=Depends(get_redis_optional)) -> dict:
    """Resultados de la prueba A/B de la mascota en las páginas públicas."""
    from app.services import mascot_ab

    if redis is None:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    return await mascot_ab.results(redis)


# ─── Piloto: cómo van los negocios (en vez de PostHog) ──────────────────────


@router.get("/admin/pilot")
async def pilot_overview(db: AsyncSession = Depends(get_db)):
    """Embudo, altas por semana y uso de cada negocio, sacado de la base
    (decisión 2026-10-15: no se usa PostHog). Las cuentas admin no cuentan."""
    from datetime import timedelta

    from app.models.appointment import Appointment
    from app.models.campaign import Campaign
    from app.models.contact import Contact
    from app.models.conversation import Conversation
    from app.models.order import Order
    from app.models.sale import Sale

    now = datetime.now(timezone.utc)
    since_30 = now - timedelta(days=30)
    owners = (await db.execute(
        select(User).where(User.role != "admin").order_by(desc(User.created_at))
    )).scalars().all()

    verified = [u for u in owners if u.email_verified]
    paying = [u for u in owners if u.subscription_status == "active"]
    funnel = {
        "registrados": len(owners),
        "verificaron_correo": len(verified),
        "en_prueba": sum(1 for u in owners if u.subscription_status == "trial"),
        "pagando": len(paying),
        # Tienen cliente en Stripe (abrieron el pago) pero siguen sin pagar.
        "abrieron_pago_sin_pagar": sum(1 for u in owners if u.stripe_customer_id and u.subscription_status == "trial"),
        "cancelaron": sum(1 for u in owners if u.subscription_status == "churned" or u.cancel_at_period_end),
        "prueba_a_pago_pct": round(100 * len(paying) / len(verified), 1) if verified else 0.0,
    }

    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    weeks = []
    for i in range(7, -1, -1):
        start = week_start - timedelta(weeks=i)
        end = start + timedelta(weeks=1)
        in_week = [u for u in owners if start <= u.created_at < end]
        weeks.append({"semana": start.date().isoformat(), "registros": len(in_week),
                      "verificaron": sum(1 for u in in_week if u.email_verified)})

    ids = [u.id for u in owners]

    async def per_owner(model, *where) -> dict:
        if not ids:
            return {}
        rows = await db.execute(
            select(model.advertiser_id, func.count()).where(model.advertiser_id.in_(ids), *where)
            .group_by(model.advertiser_id)
        )
        return dict(rows.all())

    chats = await per_owner(Conversation, Conversation.last_activity >= since_30)
    citas = await per_owner(Appointment, Appointment.created_at >= since_30)
    pedidos = await per_owner(Order, Order.created_at >= since_30)
    campanas = await per_owner(Campaign, Campaign.created_at >= since_30)
    contactos = await per_owner(Contact)
    ventas = await per_owner(Sale, Sale.created_at >= since_30)
    vendido = {}
    if ids:
        rows = await db.execute(
            select(Sale.advertiser_id, func.sum(Sale.amount))
            .where(Sale.advertiser_id.in_(ids), Sale.created_at >= since_30)
            .group_by(Sale.advertiser_id)
        )
        vendido = {k: float(v) for k, v in rows.all()}

    negocios = [{
        "id": str(u.id),
        "negocio": u.business_name or "(sin nombre)",
        "email": u.email,
        "verificado": u.email_verified,
        "estado": u.subscription_status,
        "plan": u.current_plan,
        "alta": u.created_at,
        "ultimo_acceso": u.last_seen_at,
        "prueba_vence": u.plan_expires_at if u.subscription_status == "trial" else None,
        "chats_30d": chats.get(u.id, 0),
        "citas_30d": citas.get(u.id, 0),
        "pedidos_30d": pedidos.get(u.id, 0),
        "campanas_30d": campanas.get(u.id, 0),
        "contactos": contactos.get(u.id, 0),
        "ventas_30d": ventas.get(u.id, 0),
        "vendido_30d": vendido.get(u.id, 0.0),
    } for u in owners]
    return {"embudo": funnel, "semanas": weeks, "negocios": negocios}
