"""Public AdRadio-hosted landing pages — /api/v1/public/site/{slug}

Serves only the same public-safe subset of fields as widget_preview
(app/api/v1/widget.py) — no auth, embedded on the public internet.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limiter import limiter
from app.database import get_db
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/site", tags=["public-site"])


def _product_out(p: Product, sales_count: int) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description or "",
        "price": str(p.price) if p.price is not None else None,
        "category": p.category or "",
        "photo_url": p.photo_url or "",
        "sales_count": sales_count,
    }


@router.get("/{slug}")
@limiter.limit("30/minute")
async def get_public_site(request: Request, slug: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Public data to render an advertiser's AdRadio-hosted landing page."""
    result = await db.execute(select(User).where(User.slug == slug.lower()))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Página no encontrada")
    return {
        "advertiser_id": str(user.id),
        "business_name": user.business_name or "",
        "business_category": user.business_category or "",
        "city": user.city or "",
        "agent": user.bot_name or "Asistente",
        "greeting": user.widget_greeting or "¡Hola! ¿En qué puedo ayudarte?",
        "color": user.widget_color or "#25D366",
        "tagline": user.landing_tagline or "",
    }


@router.get("/{slug}/products")
@limiter.limit("30/minute")
async def get_public_site_products(request: Request, slug: str, db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Public-safe active catalog for an advertiser's AdRadio-hosted landing page."""
    result = await db.execute(select(User).where(User.slug == slug.lower()))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Página no encontrada")

    products_result = await db.execute(
        select(Product)
        .where(Product.advertiser_id == user.id, Product.active.is_(True))
        .order_by(Product.category, Product.name)
    )
    products = products_result.scalars().all()

    sales_result = await db.execute(
        select(OrderItem.product_id, func.count())
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.advertiser_id == user.id, Order.state == "confirmed")
        .group_by(OrderItem.product_id)
    )
    sales_counts = dict(sales_result.all())

    return [_product_out(p, sales_counts.get(p.id, 0)) for p in products]


@router.get("/{slug}/products/{product_id}")
@limiter.limit("30/minute")
async def get_public_site_product(
    request: Request, slug: str, product_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    """Single-product detail — powers the shareable individual product page
    (/sitio/{slug}/producto/{id}) and the crawler-facing OG preview route in
    main.py's serve_spa. Same public-safe shape as the list endpoint above,
    plus the business name/slug so the detail page doesn't need a second
    round-trip just to show "de {business_name}"."""
    result = await db.execute(select(User).where(User.slug == slug.lower()))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Página no encontrada")

    product_result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.advertiser_id == user.id,
            Product.active.is_(True),
        )
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    sales_count = await db.scalar(
        select(func.count(OrderItem.id))
        .join(Order, Order.id == OrderItem.order_id)
        .where(OrderItem.product_id == product.id, Order.state == "confirmed")
    )

    out = _product_out(product, sales_count or 0)
    out["business_name"] = user.business_name or ""
    out["slug"] = user.slug or slug
    return out
