"""Extracts rich product-card data from a bot reply's text, for chat
surfaces (widget, marketing-site demo chat) that can't rely on WhatsApp's
client-side link-preview behavior — a plain browser `<div>` never fetches
og:* tags on its own. Built 2026-08-13 after confirming the widget/demo
chat render bot messages via `.textContent` (plain text, not even a
clickable link), unlike WhatsApp which at least auto-linkifies.

Both catalog_service.py's WhatsApp reply and this module's callers embed
the SAME /p/{advertiser_id}/{product_id} URL shape (see public_site.py's
product_router) — this module just finds those URLs in already-generated
reply text and resolves them to real Product rows, so the frontend can
render an actual card instead of parsing raw text itself.
"""
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product

_PRODUCT_LINK_RE = re.compile(
    r"/p/([0-9a-fA-F-]{36})/([0-9a-fA-F-]{36})"
)


def _format_price(price) -> str | None:
    return f"${price:,.2f}" if price is not None else None


async def extract_product_cards(reply_text: str, db: AsyncSession, *, limit: int = 5) -> list[dict]:
    """Scans *reply_text* for /p/{advertiser_id}/{product_id} links and
    resolves each to a public-safe card dict. Silently skips anything that
    doesn't resolve to a real, active product (deleted/deactivated since
    the link was generated, or a malformed match) — a missing card is a
    minor visual gap, not worth failing the whole chat reply over."""
    matches = _PRODUCT_LINK_RE.findall(reply_text)[:limit]
    if not matches:
        return []

    cards = []
    seen_ids: set[str] = set()
    for advertiser_id_str, product_id_str in matches:
        if product_id_str in seen_ids:
            continue
        try:
            advertiser_id = uuid.UUID(advertiser_id_str)
            product_id = uuid.UUID(product_id_str)
        except ValueError:
            continue

        result = await db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.advertiser_id == advertiser_id,
                Product.active.is_(True),
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            continue

        seen_ids.add(product_id_str)
        cards.append({
            "url": f"/p/{advertiser_id}/{product_id}",
            "name": product.name,
            "price": _format_price(product.price),
            "photo_url": product.photo_url or "",
        })

    return cards
