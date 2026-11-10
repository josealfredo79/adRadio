"""Botones al mostrar un producto en WhatsApp (spec
docs/specs/2026-11-09-botones-producto-whatsapp.md).

El cliente toca en vez de escribir: debajo de un producto salen "Lo quiero" y
"Otra pregunta", y "Lo quiero" arranca el pedido con ese producto; cada paso
del pedido con opciones (confirmar, entrega, pago) lleva sus botones. Son
botones de respuesta dentro de la plática que abrió el cliente: no son
plantillas ni cuestan más. El botón llega como su título (meta_incoming)."""
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.contact import Contact
from app.models.product import Product

WANT = "🛒 Lo quiero"
OTHER = "❓ Otra pregunta"
PRODUCT_BUTTONS = [WANT, OTHER]

YES, NO = "✅ Sí", "❌ No"
CONFIRM_BUTTONS = [YES, NO]
HOME, PICKUP = "🏠 A domicilio", "🏪 Recojo en tienda"
DELIVERY_BUTTONS = [HOME, PICKUP]
ORDER_IN_PROGRESS = ("pending_confirmation", "collecting_name", "collecting_address", "collecting_payment")
PAYMENT_BUTTONS = ["💵 Efectivo", "💳 Tarjeta", "🏦 Transferencia"]

TAP_PREFIX = "want:"

OTHER_REPLY = "¡Claro! ¿Qué te gustaría saber? 😊"
GONE_REPLY = "Uy, ese producto ya no está disponible 🙏 ¿Te ayudo con algo más?"

_LEADING_SYMBOLS = re.compile(r"^[^\w¿¡]+", re.UNICODE)
_PRODUCT_LINK = re.compile(r"/p/([0-9a-f-]{36})/([0-9a-f-]{36})")
_PICKUP_WORDS = ("recojo", "recoger", "recoge", "paso por", "en tienda", "en el local", "voy por")


def plain(text: str | None) -> str:
    """El texto sin el dibujito del botón: "💵 Efectivo" → "Efectivo"."""
    return _LEADING_SYMBOLS.sub("", (text or "").strip()).strip()


def is_tap(text: str | None, button: str) -> bool:
    """¿Tocó este botón (o escribió lo mismo)?"""
    return plain(text).lower() == plain(button).lower()


def product_buttons(product: Product) -> list[tuple[str, str]]:
    """Con el producto en el id del botón: si en la plática se habló de otro
    después, "Lo quiero" sigue siendo de ESTE (revisor-dinero, 2026-11-09)."""
    return [(f"{TAP_PREFIX}{product.id}", WANT), ("other", OTHER)]


def parse_tap(text: str | None) -> tuple[str | None, uuid.UUID | None]:
    """"want:<id>" → (WANT, id). Cualquier otra cosa se queda igual."""
    text = (text or "").strip()
    if text.startswith(TAP_PREFIX):
        try:
            return WANT, uuid.UUID(text[len(TAP_PREFIX):])
        except ValueError:
            return WANT, None
    return text, None


async def product_by_id(db: AsyncSession, advertiser_id: uuid.UUID, product_id: uuid.UUID) -> Product | None:
    return (await db.execute(
        select(Product).where(Product.id == product_id, Product.advertiser_id == advertiser_id)
    )).scalar_one_or_none()


def is_button_tap(text: str | None, button: str) -> bool:
    """¿Tocó el botón? Llega su título exacto, con dibujito: así "lo quiero"
    escrito sigue siendo canjear un cupón (coupon_service) y no un pedido."""
    return (text or "").strip() == button


def name_buttons(contact: Contact | None) -> list[str]:
    """Su nombre de WhatsApp como botón, si parece nombre (no un teléfono)."""
    name = ((contact.name if contact else None) or "").strip()
    if not name or not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", name):
        return []
    return [f"✅ {name}"[:20]]


def chosen_name(text: str | None, contact: Contact | None) -> str:
    """El nombre del pedido. Si tocó el botón de su nombre (cortado a 20
    letras por WhatsApp), va el nombre completo de su WhatsApp."""
    if contact is not None and name_buttons(contact) == [(text or "").strip()]:
        return contact.name.strip()
    return plain(text) or (text or "").strip()


def delivery_choice(text: str | None) -> str | None:
    """"home" = quiere domicilio sin dar dirección aún; "pickup" = recoge;
    None = escribió otra cosa (se toma como su dirección)."""
    lowered = plain(text).lower()
    if is_tap(text, HOME) or lowered in ("domicilio", "a domicilio", "envío", "envio"):
        return "home"
    if is_tap(text, PICKUP) or any(w in lowered for w in _PICKUP_WORDS):
        return "pickup"
    return None


def photo_for_header(product: Product | None) -> str | None:
    """La foto va de encabezado solo si está en nuestro almacenamiento: Meta la
    descarga después de aceptar el mensaje, y si no puede, el mensaje no llega
    y ya no hay respaldo a texto."""
    url = (product.photo_url if product else None) or ""
    base = (settings.CF_R2_PUBLIC_URL or "").rstrip("/")
    return url if base.startswith("https://") and url.startswith(f"{base}/") else None


async def offered_product(db: AsyncSession, advertiser_id: uuid.UUID, messages: list[dict]) -> Product | None:
    """El producto al que se refiere el "Lo quiero": el del último link de
    producto que le mandó el bot en esta plática (aunque ya esté dado de baja,
    para poder decírselo)."""
    base = settings.BASE_URL.rstrip("/")
    for m in reversed([m for m in messages if m.get("role") == "assistant"][-6:]):
        content = m.get("content") or ""
        for match in reversed(list(_PRODUCT_LINK.finditer(content))):
            if base and base not in content:
                continue
            adv, pid = match.groups()
            if adv != str(advertiser_id):
                continue
            product = (await db.execute(
                select(Product).where(Product.id == uuid.UUID(pid), Product.advertiser_id == advertiser_id)
            )).scalar_one_or_none()
            if product:
                return product
    return None
