"""Catalog Q&A — channel-agnostic, shared between WhatsApp and the widget.

Purely additive: only answers "what do you sell" style questions with the
real Product catalog. Never touches Order/the pedido free-text flow, and
never creates any row — this is a read-only reply, same spirit as
availability_service.py's read-only slot lookup.
"""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.user import User
from app.services.claude_service import detect_catalog_intent

NO_CATALOG_REPLY = "Por ahora no tenemos un catálogo publicado, pero puedes preguntarme directamente lo que buscas 😊"

_STOPWORDS: frozenset[str] = frozenset(["de", "la", "el", "los", "las", "un", "una", "y", "con"])
_QUANTITY_RE = re.compile(r"\d+")


async def get_active_products(db: AsyncSession, advertiser_id) -> list[Product]:
    result = await db.execute(
        select(Product)
        .where(Product.advertiser_id == advertiser_id, Product.active.is_(True))
        .order_by(Product.category, Product.name)
    )
    return list(result.scalars().all())


def _format_price(price) -> str:
    return f"${price:,.2f}" if price is not None else "Cotizar"


def format_catalog_text(products: list[Product]) -> str:
    lines = ["📋 *Nuestro catálogo:*\n"]
    current_category: str | None = "__unset__"
    for p in products:
        category = p.category or None
        if category != current_category:
            if category:
                lines.append(f"\n*{category}*")
            current_category = category
        lines.append(f"• {p.name} — {_format_price(p.price)}")
    return "\n".join(lines)


async def handle_catalog_query(db: AsyncSession, advertiser: User, message: str) -> str | None:
    """Returns the catalog reply if *message* asks for it, or None (caller
    keeps going with its normal flow: pedidos, citas, RAG, etc.)."""
    if not detect_catalog_intent(message):
        return None
    products = await get_active_products(db, advertiser.id)
    if not products:
        return NO_CATALOG_REPLY
    return format_catalog_text(products)


def _significant_words(name: str) -> list[str]:
    return [w for w in name.lower().split() if w not in _STOPWORDS]


def _extract_quantity(text_lower: str, word: str) -> int:
    """Best-effort: grabs the first number near *word* in *text_lower*,
    defaults to 1. No attempt to parse spelled-out numbers ("una", "dos")."""
    idx = text_lower.find(word)
    if idx == -1:
        return 1
    window = text_lower[max(0, idx - 15):idx]
    match = _QUANTITY_RE.search(window)
    return int(match.group()) if match else 1


def match_products_in_text(products: list[Product], text: str) -> list[tuple[Product, int]]:
    """Best-effort, $0-cost match of free-text order items (e.g. "2 pizzas de
    pepperoni") against the advertiser's active catalog — same
    keyword-substring style as detect_order_intent/detect_catalog_intent, no
    LLM call.

    Deliberately substring-based (not whole-word) so a product word like
    "pizza" matches inside the customer's "pizzas" without real
    lemmatization. Known limitation: single-word product names can match
    loosely (e.g. a product named "Coca" matches any message containing that
    substring). This only feeds the "most sold" counter — it never changes
    what the advertiser sees/fulfills, which always reads Order.items_raw
    directly, so a bad match here can never break an actual order.
    """
    text_lower = text.lower()
    matches: list[tuple[Product, int]] = []
    for product in products:
        words = _significant_words(product.name)
        if not words:
            continue
        if all(word in text_lower for word in words):
            matches.append((product, _extract_quantity(text_lower, words[0])))
    return matches
