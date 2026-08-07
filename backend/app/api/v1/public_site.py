"""Public AdRadio-hosted landing pages — /api/v1/public/site/{slug}

Serves only the same public-safe subset of fields as widget_preview
(app/api/v1/widget.py) — no auth, embedded on the public internet.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limiter import limiter
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/site", tags=["public-site"])


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
