"""Recordatorio al dueño: "sube eso al Catálogo".

Cuando el dueño contesta "¿Tienen fundas?" (por el central o guardando la
tarjeta del Inbox) y las fundas no están en su Catálogo, se le recuerda darlas
de alta. Si contestó que NO hay, también que borre esa respuesta cuando ya
tenga, porque si no el bot seguirá diciendo que no hay (prueba con IA real
2026-11-05: con "Funda $120" en el catálogo y "no tenemos fundas" guardado,
el bot dijo "no tenemos" 3 de 3 veces).

Solo texto, sin IA: si no reconoce la pregunta, no dice nada.
"""
import logging
import re
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product

logger = logging.getLogger(__name__)

# "¿Tienen fundas?", "venden micas", "¿manejan cargadores tipo C?", "hay pastel de 3 leches?"
_ASKS_HAVE = re.compile(
    r"\b(?:tienen|tienes|tiene|venden|vendes|vende|manejan|manejas|maneja|hay|ofrecen|ofreces)\s+(.+)"
)
_ARTICLES = {"el", "la", "los", "las", "un", "una", "unos", "unas", "algun", "alguna", "algunos", "algunas"}
# No son productos del Catálogo: "¿tienen servicio a domicilio?", "¿hay estacionamiento?"
_NOT_PRODUCTS = re.compile(
    r"\b(domicilio|envio|envios|entrega|entregas|pago|pagos|tarjeta|transferencia|factura|facturan|"
    r"estacionamiento|garantia|descuento|descuentos|promo|promocion|promociones|oferta|ofertas|cita|citas|"
    r"credito|meses|apartado|horario|abierto|lugar|sucursal|sucursales|wifi|bano|cambio|cambios|devolucion)\b"
)
_MAX_WORDS = 4


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def _stem(word: str) -> str:
    """fundas → funda, cargadores → cargador, micas → mica."""
    if len(word) > 4 and word.endswith("es") and word[-3] not in "aeiou":
        return word[:-2]
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def asked_item(question: str) -> str | None:
    """Lo que el cliente preguntó si tienen ("fundas"), o None si no es eso."""
    m = _ASKS_HAVE.search(_plain(question))
    if not m:
        return None
    words = re.findall(r"[a-z0-9ñ]+", m.group(1))
    while words and words[0] in _ARTICLES:
        words = words[1:]
    if not words or len(words) > _MAX_WORDS or _NOT_PRODUCTS.search(" ".join(words)):
        return None
    # El texto original (con acentos) para el mensaje: mismas palabras, mismo orden.
    original = re.findall(r"[\wñÑ]+", question)
    by_plain = {_plain(w): w for w in original}
    return " ".join(by_plain.get(w, w) for w in words)


def _in_catalog(item: str, names: list[str]) -> bool:
    stems = [_stem(w) for w in re.findall(r"[a-z0-9ñ]+", _plain(item)) if len(w) >= 3]
    if not stems:
        return True  # nada que buscar: mejor no recordar de más
    return any(all(s in _plain(name) for s in stems) for name in names)


async def catalog_reminder(db: AsyncSession, advertiser_id: uuid.UUID, question: str, answer: str) -> str:
    """El recordatorio para el dueño, o "" si no aplica o algo falla."""
    try:
        item = asked_item(question)
        if not item:
            return ""
        names = (await db.execute(
            select(Product.name).where(Product.advertiser_id == advertiser_id, Product.active.is_(True))
        )).scalars().all()
        if _in_catalog(item, list(names)):
            return ""
        if re.match(r"\s*no\b", _plain(answer)):
            return (
                f"📌 Cuando ya tengas {item}, da de alta el producto en Catálogo con precio y foto, y borra "
                "esta respuesta en Base de conocimiento; si no, el bot seguirá diciendo que no hay."
            )
        return (
            f"📌 Da de alta {item} en Catálogo con precio y foto: así el bot muestra la foto y el precio, "
            "y el cliente puede pedir directo."
        )
    except Exception:
        logger.warning("[CATALOG REMINDER] failed", exc_info=True)
        return ""
