"""Catalog Q&A — channel-agnostic, shared between WhatsApp and the widget.

Purely additive: only answers "what do you sell" style questions with the
real Product catalog. Never touches Order/the pedido free-text flow, and
never creates any row — this is a read-only reply, same spirit as
availability_service.py's read-only slot lookup.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.user import User
from app.services.claude_service import detect_catalog_intent

NO_CATALOG_REPLY = "Por ahora no tenemos un catálogo publicado, pero puedes preguntarme directamente lo que buscas 😊"


async def _get_active_products(db: AsyncSession, advertiser_id) -> list[Product]:
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
    products = await _get_active_products(db, advertiser.id)
    if not products:
        return NO_CATALOG_REPLY
    return format_catalog_text(products)
