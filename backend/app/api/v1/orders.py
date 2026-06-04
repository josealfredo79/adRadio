"""
Orders router — /api/v1/orders
List and manage orders received via the WhatsApp bot.
"""
import logging
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.order import Order
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderStateUpdate(BaseModel):
    state: Literal["confirmed", "cancelled"]


@router.get("")
async def list_orders(
    state: Optional[str] = Query(None, description="Filter by state: collecting_name, collecting_address, collecting_payment, confirmed, cancelled"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List orders for the authenticated advertiser, newest first."""
    q = (
        select(Order)
        .options(selectinload(Order.contact))
        .where(Order.advertiser_id == current_user.id)
    )
    if state:
        q = q.where(Order.state == state)
    q = q.order_by(Order.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(q)
    orders = result.scalars().all()

    # Count total
    count_q = select(func.count()).select_from(Order).where(Order.advertiser_id == current_user.id)
    if state:
        count_q = count_q.where(Order.state == state)
    total = (await db.execute(count_q)).scalar() or 0

    items = []
    for o in orders:
        contact_phone = o.contact.phone if o.contact else None

        items.append({
            "id": str(o.id),
            "order_number": o.order_number,
            "state": o.state,
            "items_raw": o.items_raw,
            "customer_name": o.customer_name,
            "customer_phone": contact_phone,
            "delivery_address": o.delivery_address,
            "payment_method": o.payment_method,
            "confirmed_at": o.confirmed_at.isoformat() if o.confirmed_at else None,
            "created_at": o.created_at.isoformat(),
        })

    return {"total": total, "items": items}


@router.patch("/{order_id}/state")
async def update_order_state(
    order_id: UUID,
    body: OrderStateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Update order state (e.g. mark as cancelled or confirmed manually)."""
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.advertiser_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.state = body.state
    if body.state == "confirmed" and not order.confirmed_at:
        order.confirmed_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info("Order %s state updated to %s by user %s", order.order_number, body.state, current_user.id)
    return {"id": str(order.id), "state": order.state}
