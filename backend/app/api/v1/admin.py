"""
Admin endpoints for subscription management.
"""
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.api.v1.payments import PLANS
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
    whatsapp_number_source: str
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
