"""
Orders router — /api/v1/orders
List and manage orders received via the WhatsApp bot.
"""
import logging
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.rate_limiter import limiter
from app.database import get_db
from app.models.contact import Contact
from app.models.order import Order
from app.models.user import User
from app.services.loyalty_service import add_stamp, notify_stamp, remove_stamp
from app.services.sales_service import (
    SaleError,
    parse_amount,
    remove_order_sale,
    set_order_sale,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderStateUpdate(BaseModel):
    state: Literal["confirmed", "cancelled"]
    # Cuánto fue el pedido, opcional al confirmar ("Cobré", docs/specs/2026-10-17-cobre.md).
    amount: str | float | None = None


@router.get("")
async def list_orders(
    state: str | None = Query(None, description="Filter by state: collecting_name, collecting_address, collecting_payment, confirmed, cancelled"),
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

    from app.services.order_handoff import customer_wa_link, order_total

    items = []
    for o in orders:
        contact_phone = o.contact.phone if o.contact else None
        wa_link = (customer_wa_link(current_user, o, contact_phone, await order_total(db, o))
                   if o.state == "confirmed" else None)

        items.append({
            "id": str(o.id),
            "order_number": o.order_number,
            "state": o.state,
            "items_raw": o.items_raw,
            "customer_name": o.customer_name,
            "customer_phone": contact_phone,
            "customer_wa_link": wa_link,
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

    amount = None
    if body.state == "confirmed" and body.amount not in (None, ""):
        try:
            amount = parse_amount(body.amount)
        except SaleError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    order.state = body.state
    if body.state == "confirmed" and not order.confirmed_at:
        order.confirmed_at = datetime.now(timezone.utc)
    # Tarjeta de lealtad: pedido confirmado sella; uno cancelado (ej. un
    # pedido de broma) pierde su sello si aún no se usó en un premio.
    stamped = False
    if body.state == "confirmed":
        stamped = await add_stamp(db, current_user, order.contact_id, "order", str(order.id))
        if amount is not None:
            await set_order_sale(db, current_user, order, amount)
    else:
        await remove_stamp(db, order.contact_id, "order", str(order.id))
        await remove_order_sale(db, current_user, order)
    await db.commit()
    if stamped:
        await notify_stamp(db, current_user, order.contact_id)
    logger.info("Order %s state updated to %s by user %s", order.order_number, body.state, current_user.id)
    return {"id": str(order.id), "state": order.state}


# Link corto del aviso de WhatsApp al dueño → WhatsApp del cliente con el mensaje
# ya escrito (spec 2026-10-21-pedido-se-entrega-al-dueno). Público: lo abre el
# dueño desde su celular sin sesión; la firma es la llave.
public_router = APIRouter(prefix="/o", tags=["orders"])


@public_router.get("/{token}", include_in_schema=False)
@limiter.limit("30/minute")
async def open_customer_whatsapp(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    from app.services.order_handoff import (
        customer_wa_link,
        order_total,
        read_owner_short_link,
    )

    order_id = read_owner_short_link(token)
    order = await db.get(Order, order_id) if order_id else None
    contact = await db.get(Contact, order.contact_id) if order and order.contact_id else None
    advertiser = await db.get(User, order.advertiser_id) if order else None
    link = customer_wa_link(advertiser, order, contact.phone, await order_total(db, order)) if contact else None
    if not link:
        raise HTTPException(status_code=404, detail="Link no válido")
    return RedirectResponse(link, status_code=302)
