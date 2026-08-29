"""
Bot Closer — recordatorio único antes de que venza una oferta.
Patrón espejo de appointment_ops.send_24h_reminders: el beat cada 5 min llama
aquí, se hace poll de los cupones `source="closer"` que están por vencer y no
se han canjeado ni recordado, y se manda un nudge respetando la ventana de 24h.
"""
import logging
from datetime import timedelta

from sqlalchemy import select

logger = logging.getLogger(__name__)


async def send_closer_reminders(db, now):
    from app.models.contact import Contact
    from app.models.conversation import Conversation
    from app.models.coupon import Coupon
    from app.models.user import User
    from app.services.coupon_service import is_expired
    from app.services.meta_service import send_whatsapp
    from app.services.whatsapp_window import is_window_open

    result = await db.execute(
        select(Coupon).where(
            Coupon.source == "closer",
            Coupon.redeemed_at.is_(None),
            Coupon.reminder_sent_at.is_(None),
            Coupon.expires_at > now + timedelta(minutes=20),
            Coupon.expires_at <= now + timedelta(minutes=90),
        )
    )
    for coupon in result.scalars().all():
        if is_expired(coupon.expires_at) or not coupon.contact_id:
            coupon.reminder_sent_at = now
            continue

        advertiser = (await db.execute(
            select(User).where(User.id == coupon.advertiser_id)
        )).scalar_one_or_none()
        contact = (await db.execute(
            select(Contact).where(Contact.id == coupon.contact_id)
        )).scalar_one_or_none()
        if not advertiser or not contact or not contact.phone:
            coupon.reminder_sent_at = now
            continue

        conv = (await db.execute(
            select(Conversation).where(
                Conversation.advertiser_id == advertiser.id,
                Conversation.contact_id == contact.id,
                Conversation.status == "active",
            )
        )).scalar_one_or_none()

        # Es un nudge, no vale gastar una plantilla — si la ventana está cerrada
        # se marca como recordado y se deja pasar.
        if is_window_open(conv):
            fn = contact.name.split()[0] if contact.name else ""
            fn = "" if (fn.startswith("+") or fn.isdigit()) else fn
            hi = f"{fn}, " if fn else ""
            label = coupon.description or "apartado"
            try:
                await send_whatsapp(
                    contact.phone,
                    f"{hi}tu *{label}* vence en menos de 1 hora ⏰. "
                    f"¿Lo confirmo? Responde *CANJEAR*.",
                    advertiser=advertiser,
                )
            except Exception:
                logger.warning("[CLOSER] reminder send failed for coupon=%s", coupon.id, exc_info=True)

        coupon.reminder_sent_at = now
