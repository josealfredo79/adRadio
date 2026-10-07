"""El producto del que se está hablando, para mostrar su foto.

- WhatsApp: se agrega el link de su página (/p/{negocio}/{producto}). WhatsApp
  arma la vista previa con la foto, nombre y precio — en el MISMO mensaje, sin
  costo extra (mandar la foto aparte serían dos mensajes cobrados). Y al
  tocarla, el cliente sigue en la web.
- Web: se devuelve el producto para que el chat ponga su tarjeta con foto.

Solo si se habla de UN producto: con varios, mejor no adivinar.
"""
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.product import Product
from app.services.catalog_service import get_active_products, match_products_in_text

_URL_RE = re.compile(r"https?://\S+")


def product_url(product: Product) -> str:
    return f"{settings.BASE_URL}/p/{product.advertiser_id}/{product.id}"


async def mentioned_product(db: AsyncSession, advertiser_id, customer_text: str, reply: str) -> Product | None:
    """Primero lo que pidió el cliente; si ahí no queda claro, lo que contestó el bot."""
    if "/p/" in (reply or ""):
        return None  # ya trae el link de un producto
    products = await get_active_products(db, advertiser_id)
    if not products:
        return None
    for text in (customer_text or "", reply or ""):
        found = {p.id: p for p, _qty in match_products_in_text(products, text)}
        if len(found) == 1:
            return next(iter(found.values()))
        if len(found) > 1:
            return None
    return None


RECENT_TURNS = 6


def link_sent_recently(product: Product, messages: list[dict]) -> bool:
    """¿Ya le mandamos este link hace poco? Si el cliente hace varias preguntas
    seguidas del mismo producto ("¿tiene jardín?", "¿cuántos baños?"), el link
    con foto va una vez, no en cada respuesta."""
    url = product_url(product)
    recent = [m for m in messages if m.get("role") == "assistant"][-RECENT_TURNS:]
    return any(url in (m.get("content") or "") for m in recent)


def with_product_link(reply: str, product: Product) -> str:
    """WhatsApp previsualiza el PRIMER link del mensaje: si la respuesta ya trae
    otro, el del producto va arriba para que la foto sea la suya."""
    line = f"📸 *{product.name}*, fotos y detalles:\n{product_url(product)}"
    if _URL_RE.search(reply):
        return f"{line}\n\n{reply}"
    return f"{reply}\n\n{line}"
