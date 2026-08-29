"""
Bot Closer — cuando una conversación está "hot" (intención de compra alta), el
bot añade a su respuesta una oferta con **caducidad real**: un Coupon para ese
contacto que de verdad expira. El cliente la cierra respondiendo CANJEAR (el
handler de canje en inbound_pipeline.py ya sirve para cualquier cupón del
contacto) o agendando una cita.

Nada de escasez inventada: la frase de "quedan N lugares" solo se dice cuando
el negocio tiene agenda y el número sale de disponibilidad real
(availability_service). Los negocios de producto no tienen inventario en el
sistema, así que ahí la oferta es solo urgencia por tiempo.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.user import User
from app.services.availability_service import get_available_slots
from app.services.coupon_service import default_expiry, format_coupon_in_message, generate_coupon_code

logger = logging.getLogger(__name__)

CLOSER_DEFAULTS = {
    "hold_hours": 2,
    "discount_type": "percentage",
    "discount_value": 0,
    "label": "Apartado especial",
    "message": None,
}


def _first_name(name: str | None) -> str:
    if not name:
        return ""
    fn = name.split()[0]
    return "" if (fn.startswith("+") or fn.isdigit()) else fn


async def _scarcity_note(db: AsyncSession, advertiser: User) -> str | None:
    """Frase de escasez REAL — solo negocios con agenda configurada."""
    if not advertiser.business_hours:
        return None
    today = date.today()
    for label, day in (("hoy", today), ("mañana", today + timedelta(days=1))):
        try:
            slots = await get_available_slots(db, advertiser, day)
        except Exception:
            logger.warning("[CLOSER] get_available_slots failed", exc_info=True)
            return None
        if 0 < len(slots) <= 3:
            return f"Para {label} solo quedan {len(slots)} lugares."
        if slots:
            return None
    return None


async def build_closer_offer(
    db: AsyncSession, advertiser: User, contact: Contact
) -> tuple[Coupon, str] | None:
    """Devuelve (coupon, texto_de_oferta) o None si no aplica.

    Deja el Coupon en la sesión (sin commit) para que se persista con el resto
    del pipeline.
    """
    cfg = {**CLOSER_DEFAULTS, **(advertiser.closer_config or {})}
    if not cfg.get("enabled"):
        return None

    now = datetime.now(timezone.utc)
    existing = await db.execute(
        select(Coupon).where(
            Coupon.contact_id == contact.id,
            Coupon.source == "closer",
            Coupon.redeemed_at.is_(None),
            Coupon.expires_at > now,
        ).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        return None  # ya tiene una oferta activa — no re-ofertar

    hold_hours = int(cfg.get("hold_hours") or 2)
    coupon = Coupon(
        advertiser_id=advertiser.id,
        contact_id=contact.id,
        campaign_id=None,
        source="closer",
        code=generate_coupon_code(),
        description=(cfg.get("label") or "Apartado especial")[:255],
        discount_type=cfg.get("discount_type") or "percentage",
        discount_value=cfg.get("discount_value") or 0,
        expires_at=default_expiry(hours=hold_hours),
    )
    db.add(coupon)
    await db.flush()

    base = (cfg.get("message") or "").strip() or (
        f"Te aparto el precio y tu lugar por {hold_hours} "
        f"{'hora' if hold_hours == 1 else 'horas'}."
    )
    scarcity = await _scarcity_note(db, advertiser)
    text = base if not scarcity else f"{base} {scarcity}"
    text = format_coupon_in_message(text, coupon.code, coupon.expires_at, coupon.description or "")
    return coupon, text
