"""
Orders router — /api/v1/orders
List and manage orders received via the WhatsApp bot.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.contact import Contact
from app.models.order import Order
from app.models.user import User

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("")
async def list_orders(
    state: Optional[str] = Query(None, description="Filter by state: collecting_name, collecting_address, collecting_payment, confirmed, cancelled"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List orders for the authenticated advertiser, newest first."""
    q = select(Order).where(Order.advertiser_id == current_user.id)
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

    # Enrich with contact phone
    items = []
    for o in orders:
        contact_phone = None
        if o.contact_id:
            c_result = await db.execute(select(Contact).where(Contact.id == o.contact_id))
            contact = c_result.scalar_one_or_none()
            if contact:
                contact_phone = contact.phone

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
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update order state (e.g. mark as cancelled or confirmed manually)."""
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.advertiser_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Order not found")

    new_state = body.get("state")
    allowed = {"confirmed", "cancelled"}
    if new_state not in allowed:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"state must be one of {allowed}")

    order.state = new_state
    if new_state == "confirmed" and not order.confirmed_at:
        from datetime import timezone
        order.confirmed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": str(order.id), "state": order.state}
