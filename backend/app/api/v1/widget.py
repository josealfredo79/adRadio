"""Widget embebible — /api/v1/widget"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import get_current_user, get_db
from app.models.user import User

router = APIRouter(prefix="/widget", tags=["widget"])


@router.get("/snippet")
async def get_widget_snippet(
    current_user: User = Depends(get_current_user),
):
    """Return the embeddable HTML/JS snippet for this advertiser's WhatsApp widget."""
    wa_number = current_user.whatsapp_number or ""
    business = (current_user.business_name or "Nosotros").replace("'", "\\'")
    bot_name = (current_user.bot_name or "Asistente").replace("'", "\\'")

    snippet = f"""<!-- IaRadio WhatsApp Widget -->
<link rel="stylesheet" href="https://www.iaradio.online/widget/widget.css">
<script>
  window.IaRadioWidget = {{
    phone: '{wa_number}',
    business: '{business}',
    agent: '{bot_name}',
    greeting: '¡Hola! ¿En qué puedo ayudarte?',
    color: '#25D366',
  }};
</script>
<script src="https://www.iaradio.online/widget/widget.js" defer></script>
<!-- Fin IaRadio Widget -->"""

    return {"snippet": snippet}


@router.get("/preview/{advertiser_id}", include_in_schema=False)
async def widget_preview(advertiser_id: UUID, db: AsyncSession = Depends(get_db)):
    """Public endpoint to load widget config for a given advertiser (used by widget.js)."""
    result = await db.execute(select(User).where(User.id == advertiser_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404)
    return {
        "phone": user.whatsapp_number or "",
        "business": user.business_name or "",
        "agent": user.bot_name or "Asistente",
    }
