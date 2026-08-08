"""Pedidos vía widget — reutiliza el modelo `Order` y `detect_order_intent`
(claude_service.py), pero con su propia máquina de estados, invocada solo
desde el endpoint del widget. No toca inbound_pipeline.py (el camino de
producción de WhatsApp) — ver el plan de landing page/pedidos/citas para el
razonamiento completo detrás de esta decisión.

Estados: collecting_name → collecting_address → collecting_payment → confirmed.
Más simple que el de WhatsApp (sin el paso inicial de confirmación Sí/No),
porque el visitante ya escribió explícitamente lo que quiere pedir y ya dejó
sus datos de contacto antes de llegar aquí.
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.order import Order
from app.models.user import User
from app.services.claude_service import detect_order_intent

logger = logging.getLogger(__name__)

NEEDS_CONTACT_REPLY = (
    "¡Con gusto te ayudo con tu pedido! 🛒 Para poder contactarte y confirmarlo, "
    "primero déjame tus datos con el botón \"📋 Dejar mis datos\" de aquí abajo."
)


async def handle_widget_order(
    db: AsyncSession, advertiser: User, contact: Contact | None, message: str
) -> str | None:
    """Returns a reply to send instead of the RAG bot, or None if this message
    isn't order-related and the widget should fall through to answer_with_rag."""
    if contact:
        result = await db.execute(
            select(Order).where(
                Order.advertiser_id == advertiser.id,
                Order.contact_id == contact.id,
                Order.state.not_in(["confirmed", "cancelled"]),
            ).order_by(Order.created_at.desc())
        )
        pending_order = result.scalars().first()
        if pending_order:
            return await _advance(db, advertiser, contact, pending_order, message)

    if not detect_order_intent(message):
        return None

    if not contact:
        return NEEDS_CONTACT_REPLY

    return await _start(db, advertiser, contact, message)


async def _start(db: AsyncSession, advertiser: User, contact: Contact, message: str) -> str:
    count_result = await db.execute(
        select(func.count()).select_from(Order).where(Order.advertiser_id == advertiser.id)
    )
    order_count = count_result.scalar() or 0
    order = Order(
        advertiser_id=advertiser.id,
        contact_id=contact.id,
        items_raw=message.strip(),
        state="collecting_name",
        order_number=order_count + 1,
    )
    db.add(order)
    await db.commit()
    return "¡Con gusto! 🛒 ¿A qué nombre va el pedido?"


async def _advance(
    db: AsyncSession, advertiser: User, contact: Contact, order: Order, message: str
) -> str:
    message = message.strip()

    if order.state == "collecting_name":
        order.customer_name = message
        order.state = "collecting_address"
        await db.commit()
        first_name = message.split()[0] if message.split() else message
        return f"Perfecto, {first_name} 👍 ¿Cuál es tu dirección de entrega? 📍"

    if order.state == "collecting_address":
        order.delivery_address = message
        order.state = "collecting_payment"
        await db.commit()
        return "¡Anotado! 📝 ¿Cómo prefieres pagar?\nResponde: *Efectivo*, *Tarjeta* o *Transferencia* 💳"

    # order.state == "collecting_payment" — the only remaining transition
    order.payment_method = message
    order.state = "confirmed"
    order.confirmed_at = datetime.now(timezone.utc)
    await db.commit()

    await _notify_owner(advertiser, contact, order)

    return (
        f"✅ *Pedido #{order.order_number:04d} confirmado*\n\n"
        f"🛒 {order.items_raw}\n"
        f"👤 {order.customer_name}\n"
        f"📍 {order.delivery_address}\n"
        f"💳 {order.payment_method}\n\n"
        "¡Gracias! En breve te contactamos para confirmar el tiempo de entrega 🚀"
    )


async def _notify_owner(advertiser: User, contact: Contact, order: Order) -> None:
    from app.core.email import send_new_order_email

    asyncio.create_task(
        send_new_order_email(
            to=advertiser.email,
            order_number=order.order_number,
            business_name=advertiser.business_name or "Tu negocio",
            items_raw=order.items_raw or "",
            customer_name=order.customer_name or "",
            customer_phone=contact.phone or "",
            delivery_address=order.delivery_address or "",
            payment_method=order.payment_method or "",
        )
    )

    if advertiser.whatsapp_number or advertiser.phone:
        from app.services.meta_service import send_whatsapp

        owner_number = advertiser.whatsapp_number or advertiser.phone
        wa_notify = (
            f"📦 *NUEVO PEDIDO #{order.order_number:04d}* (desde tu página web)\n"
            f"────────────────\n"
            f"🛒 {order.items_raw}\n"
            f"👤 Cliente: {order.customer_name}\n"
            f"📱 Teléfono: {contact.phone}\n"
            f"📍 Dirección: {order.delivery_address}\n"
            f"💳 Pago: {order.payment_method}\n"
            f"────────────────"
        )
        try:
            await send_whatsapp(owner_number, wa_notify, advertiser=advertiser)
        except Exception:
            logger.warning("[WIDGET-ORDER] Failed to notify owner via WhatsApp", exc_info=True)
