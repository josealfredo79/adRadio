"""IaRadio toma el pedido y se lo entrega al dueño; el pago, el tiempo y la
entrega los arreglan ellos por WhatsApp (docs/specs/2026-10-21-pedido-se-entrega-al-dueno.md).

Aquí viven el texto que ve el cliente al terminar ("enviado a…", nunca
"confirmado" ni datos de pago) y el link wa.me con el mensaje ya escrito que
el dueño abre en su propio WhatsApp para contestarle."""
import hashlib
import hmac
import uuid
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.user import User
from app.services.customer_account import canonical_phone
from app.services.payment_info import payment_lines
from app.services.portal_service import _b64, _unb64

# Las semillas de "Plantillas" de antes: si el negocio las importó y no las
# cambió, se usa el texto nuevo; si las cambió, se respeta lo suyo.
OLD_SEED_CONFIRMED = ("✅ *Pedido #{{order_number}} confirmado*\n\n🛒 {{items}}\n👤 {{nombre}}\n📍 {{direccion}}\n"
                      "💳 {{pago}}\n\n¡Gracias! En breve te contactamos para confirmar el tiempo de entrega.")
OLD_SEED_OWNER_NOTIFY = ("📦 *NUEVO PEDIDO #{{order_number}}*\n────────────────\n🛒 {{items}}\n👤 Cliente: {{nombre}}\n"
                         "📱 WhatsApp: {{telefono}}\n📍 Dirección: {{direccion}}\n💳 Pago: {{pago}}\n────────────────\n"
                         "Responde a este número para contactar al cliente.")


def business_name(advertiser: User) -> str:
    return (advertiser.business_name or "").strip() or "el negocio"


def pesos(amount: float) -> str:
    return f"${amount:,.0f}" if float(amount).is_integer() else f"${amount:,.2f}"


def is_pickup(address: str | None) -> bool:
    address = (address or "").strip().lower()
    return not address or address.startswith("para recoger")


def where_text(address: str | None) -> str:
    return "Para recoger en el local" if is_pickup(address) else f"A domicilio: {address.strip()}"


async def order_total(db: AsyncSession, order: Order) -> float | None:
    """Total aprox. con los precios del catálogo; None si no hay renglones de
    catálogo (pedido escrito a mano) o alguno no tiene precio."""
    rows = (await db.execute(
        select(OrderItem.quantity, Product.price)
        .join(Product, Product.id == OrderItem.product_id, isouter=True)
        .where(OrderItem.order_id == order.id)
    )).all()
    if not rows or any(price is None for _, price in rows):
        return None
    return sum(float(price) * qty for qty, price in rows)


def sent_to_business_text(advertiser: User, order: Order, total: float | None = None) -> str:
    total_line = f" · total aprox. {pesos(total)}" if total else ""
    return (
        f"📦 *Pedido #{order.order_number:04d} enviado a {business_name(advertiser)}*\n"
        f"🛒 {order.items_raw}{total_line}\n"
        f"📍 {where_text(order.delivery_address)}\n"
        + (f"💳 {order.payment_method}\n" if order.payment_method else "")
        + "\nTe escriben por WhatsApp para confirmar tu pedido y acordar el pago 🙌"
    )


def customer_wa_link(advertiser: User, order: Order, phone: str | None, total: float | None = None) -> str | None:
    """wa.me al cliente con el mensaje que el dueño solo completa y manda."""
    digits = canonical_phone(phone)
    if not digits:
        return None
    first = (order.customer_name or "").split()[0] if (order.customer_name or "").split() else ""
    total_line = f" (total aprox. {pesos(total)})" if total else ""
    when = "Está listo para recoger en ___ min." if is_pickup(order.delivery_address) else "Te llega en ___ min."
    pay = payment_lines(advertiser, order.payment_method).strip()
    text = (
        f"Hola{' ' + first if first else ''}, te escribo de {business_name(advertiser)} por tu pedido "
        f"#{order.order_number:04d}:\n🛒 {order.items_raw}{total_line}\n📍 {where_text(order.delivery_address)}\n"
        f"{when}" + (f"\n{pay}" if pay else "")
    )
    return f"https://wa.me/{digits}?text={quote(text)}"


def with_owner_link(notice: str, link: str | None) -> str:
    """El link va en la 2.ª línea del aviso: si sale como plantilla, Meta corta
    el final a 1,024 caracteres y un pedido largo lo dejaría fuera."""
    if not link:
        return notice
    head, _, rest = notice.partition("\n")
    return f"{head}\n👉 Escribirle al cliente: {link}" + (f"\n{rest}" if rest else "")


def fill_order_template(template: str, values: dict[str, str]) -> str:
    """Las plantillas de pedido usan {{order_number}}, {{items}}, {{direccion}},
    {{pago}}, {{telefono}}, {{nombre}}, {{primer_nombre}}, {{ciudad}} y {{negocio}}."""
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def public_business_whatsapp(advertiser: User) -> str:
    """Solo el WhatsApp del negocio conectado a IaRadio, nunca el número
    personal del dueño (mismo criterio que la página pública)."""
    if advertiser.meta_connection_status == "connected" and advertiser.meta_display_phone_number:
        return advertiser.meta_display_phone_number
    return ""


# Link corto para el aviso de WhatsApp al dueño: si sale como plantilla (fuera
# de la ventana de 24 h), Meta junta el texto y lo corta a 1,024 caracteres, y
# el wa.me con el mensaje escrito no cabe. Mismo modelo que el portal: id +
# HMAC con SECRET_KEY, sin guardar nada.
_DOMAIN = b"order-wa:v1:"


def _sign(order_id: uuid.UUID) -> bytes:
    return hmac.new(settings.SECRET_KEY.encode(), _DOMAIN + order_id.bytes, hashlib.sha256).digest()[:12]


def owner_short_link(order: Order) -> str | None:
    if not settings.SECRET_KEY or order.id is None:
        return None
    base = (settings.FRONTEND_URL or "https://www.iaradio.online").rstrip("/")
    return f"{base}{settings.API_PREFIX}/o/{_b64(order.id.bytes)}.{_b64(_sign(order.id))}"


def read_owner_short_link(token: str) -> uuid.UUID | None:
    if not settings.SECRET_KEY:
        return None
    try:
        id_part, sig_part = token.split(".", 1)
        order_id = uuid.UUID(bytes=_unb64(id_part))
        sig = _unb64(sig_part)
    except (ValueError, TypeError):
        return None
    return order_id if hmac.compare_digest(sig, _sign(order_id)) else None
