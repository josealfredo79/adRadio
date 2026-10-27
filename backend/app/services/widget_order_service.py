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
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.contact import Contact
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.user import User
from app.services.catalog_service import get_active_products, match_products_in_text
from app.services.claude_service import detect_order_intent
from app.services.owner_question_service import owner_number as get_owner_number

logger = logging.getLogger(__name__)

# Un pedido a medias solo se retoma si se empezó hace poco. Sin este límite,
# un pedido abandonado hace días se "comía" el siguiente mensaje del cliente
# (ej. "me interesa la promo" se guardaba como dirección de entrega) — y con
# el portal del cliente, volver días después al chat es lo normal.
ORDER_RESUME_WINDOW = timedelta(hours=2)

NEEDS_CONTACT_REPLY = (
    "¡Con gusto te ayudo con tu pedido! 🛒 Para confirmártelo solo necesito tu "
    "nombre y tu WhatsApp — déjalos aquí abajo 👇"
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
                Order.created_at > datetime.now(timezone.utc) - ORDER_RESUME_WINDOW,
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

    active_products = await get_active_products(db, advertiser.id)
    matched = match_products_in_text(active_products, message)
    if matched:
        db.add_all([
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name_snapshot=product.name,
                quantity=qty,
            )
            for product, qty in matched
        ])

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
        if not advertiser.delivers_home:
            # Sin entrega a domicilio (o sin definir): no se pide dirección.
            order.state = "collecting_payment"
            await db.commit()
            return (f"Perfecto, {first_name} 👍 Tu pedido es para recoger en el local 🏪\n"
                    "¿Cómo prefieres pagar?\nResponde: *Efectivo*, *Tarjeta* o *Transferencia* 💳")
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
    from app.services.order_handoff import order_total, sent_to_business_text

    # Sin sello al pedir: se gana al cobrar ("Cobré $___"), así un pedido de broma no suma.
    await db.commit()

    total = await order_total(db, order)
    await _notify_owner(advertiser, contact, order, total=total)

    # IaRadio solo entrega el pedido: sin "confirmado" ni datos de pago (spec 2026-10-21).
    return sent_to_business_text(advertiser, order, total)


def where_line(order: Order, prefix: str = "") -> str:
    """La dirección del pedido, o "Para recoger en el local" si no hay."""
    address = (order.delivery_address or "").strip()
    return f"{prefix}{address}" if address else "Para recoger en el local"


async def _notify_owner(
    advertiser: User, contact: Contact, order: Order, origin: str = "desde tu página web", total: float | None = None
) -> None:
    from app.core.email import send_new_order_email
    from app.services.order_handoff import (
        customer_wa_link,
        owner_short_link,
        pesos,
        with_owner_link,
    )

    wa_link = customer_wa_link(advertiser, order, contact.phone, total)

    asyncio.create_task(
        send_new_order_email(
            to=advertiser.email,
            order_number=order.order_number,
            business_name=advertiser.business_name or "Tu negocio",
            items_raw=order.items_raw or "",
            customer_name=order.customer_name or "",
            customer_phone=contact.phone or "",
            delivery_address=where_line(order),
            payment_method=order.payment_method or "",
            wa_link=wa_link,
        )
    )

    if get_owner_number(advertiser):
        from app.services.owner_notify import notify_owner

        wa_notify = (
            f"📦 *NUEVO PEDIDO #{order.order_number:04d}* ({origin})\n"
            f"────────────────\n"
            f"🛒 {order.items_raw}\n"
            f"👤 Cliente: {order.customer_name}\n"
            f"📱 Teléfono: {contact.phone}\n"
            f"📍 {where_line(order, 'Dirección: ')}\n"
            + (f"💳 Pago: {order.payment_method}\n" if order.payment_method else "")
            + "────────────────"
        )
        link = wa_link and owner_short_link(order)
        wa_notify = with_owner_link(wa_notify, link)
        detail = " · ".join(filter(None, [
            order.items_raw, f"total aprox. {pesos(total)}" if total else "", where_line(order),
            f"Cliente: {order.customer_name}", f"Tel: {contact.phone}",
            f"Escríbele aquí: {link}" if link else "",
        ]))
        if len(detail) > 700:  # Meta también limita el cuerpo completo de la plantilla
            detail = (f"Escríbele aquí: {link} · " if link else "") + detail[:600] + "…"
        template = (settings.IARADIO_ORDER_TEMPLATE_NAME, [f"{order.order_number:04d}", detail])
        try:
            await notify_owner(advertiser, wa_notify, template=template)
        except Exception:
            logger.warning("[WIDGET-ORDER] Failed to notify owner via WhatsApp", exc_info=True)
