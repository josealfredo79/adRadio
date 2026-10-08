"""Public AdRadio-hosted landing pages — /api/v1/public/site/{slug}

Serves only the same public-safe subset of fields as widget_preview
(app/api/v1/widget.py) — no auth, embedded on the public internet.
"""
import logging
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limiter import limiter
from app.core.redis import get_redis_optional
from app.database import get_db
from app.models.customer_story import CustomerStory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.user import User
from app.services.availability_service import DEFAULT_BUSINESS_HOURS
from app.services.chat_quick_asks import chat_quick_asks
from app.services.landing_sections import DEFAULT_LANDING_SECTIONS

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
        "logo_url": user.logo_url or "",
        "hero_image_url": user.hero_image_url or "",
        "site_photos": user.site_photos or [],
        "site_about": user.site_about or "",
        "site_theme": user.site_theme or "medianoche",
        "whatsapp_number": _public_whatsapp_number(user),
        "business_hours": user.business_hours or DEFAULT_BUSINESS_HOURS,
        "landing_sections": user.landing_sections or DEFAULT_LANDING_SECTIONS,
        "slug": user.slug or "",
        # Registro con código (/q/{slug}) encendido: el chat ofrece "Hazte cliente".
        "account_available": settings.CUSTOMER_ACCOUNT_ENABLED,
        "quick_asks": chat_quick_asks(user),
    }


def _public_whatsapp_number(user: User) -> str:
    """Only surface the real, connected Meta WhatsApp Business number — never
    User.whatsapp_number (the owner's personal notification number, a
    different field entirely) — so the public footer never invites customers
    to message the owner directly."""
    if user.meta_connection_status == "connected" and user.meta_display_phone_number:
        return user.meta_display_phone_number
    return ""


def _first_name(full_name: str | None) -> str | None:
    if not full_name:
        return None
    return full_name.strip().split(" ")[0] or None


@router.get("/{slug}/stories")
@limiter.limit("30/minute")
async def get_public_site_stories(request: Request, slug: str, db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Public-safe, advertiser-scoped approved testimonials for this
    business's own landing page — distinct from GET /campaigns/stories/public
    (campaigns.py), which is the platform-wide feed used on IaRadio's own
    marketing site, not scoped to a single advertiser."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(select(User).where(User.slug == slug.lower()))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Página no encontrada")

    stories_result = await db.execute(
        select(CustomerStory)
        .options(selectinload(CustomerStory.contact))
        .where(
            CustomerStory.advertiser_id == user.id,
            CustomerStory.status == "approved",
            CustomerStory.consent_at.is_not(None),
        )
        .order_by(CustomerStory.created_at.desc())
        .limit(6)
    )
    stories = stories_result.scalars().all()

    return [
        {
            "id": str(s.id),
            # Solo el primer nombre — suficiente para dar autenticidad sin
            # exponer el nombre completo/teléfono de un contacto real.
            "contact_name": _first_name(s.contact.name if s.contact else None),
            "transcription": s.transcription,
            "media_url": s.media_url,
            "sentiment": s.sentiment,
        }
        for s in stories
    ]


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


async def _get_product_detail(db: AsyncSession, user: User, product_id: uuid.UUID, slug_fallback: str) -> dict:
    """Shared by both product-detail routes below (slug-based and
    advertiser_id-based) — same public-safe shape, same 404 behavior."""
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
    out["slug"] = user.slug or slug_fallback
    out["whatsapp_number"] = _public_whatsapp_number(user)
    out["site_theme"] = user.site_theme or "medianoche"
    out["color"] = user.widget_color or "#25D366"
    # Para abrir el chat web desde la página del producto ("Platicar sobre este producto").
    out["advertiser_id"] = str(user.id)
    out["agent"] = user.bot_name or "Asistente"
    out["greeting"] = user.widget_greeting or ""
    out["quick_asks"] = chat_quick_asks(user)
    out["business_category"] = user.business_category or ""
    out["account_available"] = settings.CUSTOMER_ACCOUNT_ENABLED
    return out


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

    return await _get_product_detail(db, user, product_id, slug)


product_router = APIRouter(prefix="/public/product", tags=["public-product"])


@product_router.get("/{advertiser_id}/{product_id}")
@limiter.limit("30/minute")
async def get_public_product_by_advertiser(
    request: Request, advertiser_id: uuid.UUID, product_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict:
    """Same single-product detail as get_public_site_product above, but
    keyed by advertiser_id (always exists) instead of slug (opt-in, many
    advertisers never publish a landing page). Built 2026-08-13 so a
    product-with-photo link sent via the WhatsApp catalog reply works for
    every advertiser regardless of whether they've set up /sitio/{slug} —
    adoption of the two features (WhatsApp vs. landing page) doesn't overlap
    reliably enough to make either a hard dependency of the other."""
    result = await db.execute(select(User).where(User.id == advertiser_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")

    return await _get_product_detail(db, user, product_id, "")


# ─── Platicar con voz con el agente de la página ─────────────────────────────
# Igual que en el portal del cliente (portal.py), pero para cualquier visitante
# de la página pública: habla en vez de escribir y el agente 3D le contesta en
# voz alta. Sin cuenta, así que límites más cortos por IP.
SITE_AUDIO_MAX_BYTES = 2 * 1024 * 1024
SITE_SPEAK_MAX_CHARS = 600


async def _site_owner(db: AsyncSession, slug: str) -> User:
    user = (await db.execute(select(User).where(User.slug == slug.lower()))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Página no encontrada")
    return user


@router.post("/{slug}/listen")
@limiter.limit("6/minute")
async def site_listen(
    request: Request,
    slug: str,
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.api.v1.voice_setup import read_transcript

    await _site_owner(db, slug)
    transcript = await read_transcript(audio, text, SITE_AUDIO_MAX_BYTES, 500, "1 minuto")
    return {"transcript": transcript[:500]}


@router.post("/{slug}/speak")
@limiter.limit("12/minute")
async def site_speak(request: Request, slug: str, body: dict, db: AsyncSession = Depends(get_db)) -> Response:
    from app.services.radio.tts import _tts_edge

    await _site_owner(db, slug)
    from app.services.speech_text import speakable

    text = speakable(str(body.get("text") or ""))[:SITE_SPEAK_MAX_CHARS]
    if not text:
        raise HTTPException(status_code=400, detail="Nada que decir")
    try:
        audio = await _tts_edge(text, "es-MX-DaliaNeural", rate="+0%", pitch="+0Hz")
    except Exception:
        logger.warning("[SITE] TTS failed", exc_info=True)
        raise HTTPException(status_code=503, detail="Voz no disponible")
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/{slug}/ab")
@limiter.limit("60/minute")
async def site_ab_event(request: Request, slug: str, body: dict, redis=Depends(get_redis_optional)) -> dict:
    """Prueba A/B de la mascota (services/mascot_ab.py). Nunca falla hacia el
    visitante: un evento perdido no debe romper la página."""
    from app.services import mascot_ab

    variant, event, visitor = str(body.get("variant") or ""), str(body.get("event") or ""), str(body.get("visitor") or "")
    if redis is None or not mascot_ab.valid(slug, variant, event, visitor):
        return {"ok": False}
    try:
        return {"ok": await mascot_ab.record(redis, slug, variant, event, visitor)}
    except Exception:
        logger.warning("[AB] record failed slug=%s", slug, exc_info=True)
        return {"ok": False}
