"""Widget embebible — /api/v1/widget"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis as AsyncRedis

from app.api.idempotency import idempotent_post, store_idempotency_response
from app.core.redis import get_redis_optional
from app.core.rate_limiter import limiter

logger = logging.getLogger(__name__)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import get_current_user, get_db
from app.models.user import User

router = APIRouter(prefix="/widget", tags=["widget"])


@router.get("/snippet")
async def get_widget_snippet(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the embeddable HTML/JS snippet for this advertiser's WhatsApp widget."""
    wa_number = current_user.whatsapp_number or ""
    business = (current_user.business_name or "Nosotros").replace("'", "\\'")
    bot_name = (current_user.bot_name or "Asistente").replace("'", "\\'")
    greeting = (current_user.widget_greeting or "¡Hola! ¿En qué puedo ayudarte?").replace("'", "\\'")
    color = current_user.widget_color or "#25D366"

    snippet = f"""<!-- IaRadio WhatsApp Widget -->
<link rel="stylesheet" href="https://www.iaradio.online/widget/widget.css">
<script>
  window.IaRadioWidget = {{
    phone: '{wa_number}',
    business: '{business}',
    agent: '{bot_name}',
    greeting: '{greeting}',
    color: '{color}',
  }};
</script>
<script src="https://www.iaradio.online/widget/widget.js" defer></script>
<!-- Fin IaRadio Widget -->"""

    return {"snippet": snippet}


@router.get("/preview/{advertiser_id}", include_in_schema=False)
@limiter.limit("10/minute")
async def widget_preview(request: Request, advertiser_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """Public endpoint to load widget config for a given advertiser (used by widget.js)."""
    result = await db.execute(select(User).where(User.id == advertiser_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404)
    return {
        "phone": user.whatsapp_number or "",
        "business": user.business_name or "",
        "agent": user.bot_name or "Asistente",
        "greeting": user.widget_greeting or "¡Hola! ¿En qué puedo ayudarte?",
        "color": user.widget_color or "#25D366",
        "position": user.widget_position or "right",
    }


@router.put("/config")
async def update_widget_config(
    request: Request,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(idempotent_post),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict:
    """Update widget customization settings for the current advertiser."""
    if "color" in body:
        color = body["color"]
        if not color.startswith("#") or len(color) not in (4, 7):
            raise HTTPException(status_code=400, detail="Color debe ser hex válido (ej. #25D366)")
        current_user.widget_color = color
    if "greeting" in body:
        if len(body["greeting"]) > 200:
            raise HTTPException(status_code=400, detail="Saludo demasiado largo (máx 200 caracteres)")
        current_user.widget_greeting = body["greeting"]
    if "position" in body:
        if body["position"] not in ("left", "right"):
            raise HTTPException(status_code=400, detail="Posición debe ser 'left' o 'right'")
        current_user.widget_position = body["position"]

    await db.commit()
    logger.info("Widget config updated for user %s", current_user.id)
    out = {"message": "Widget actualizado"}
    await store_idempotency_response(request, redis, out)
    return out


@router.get("/config")
async def get_widget_config(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return the current widget configuration."""
    return {
        "color": current_user.widget_color or "#25D366",
        "greeting": current_user.widget_greeting or "¡Hola! ¿En qué puedo ayudarte?",
        "position": current_user.widget_position or "right",
    }
