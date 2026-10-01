"""
Appointment reminder operations.
"""
import logging
from datetime import timedelta

from sqlalchemy import select

logger = logging.getLogger(__name__)


def _when(appt) -> tuple[str, str]:
    """(fecha, hora) en hora de México y en español. Antes se formateaba
    scheduled_at tal cual — llega en UTC, así que el recordatorio decía una
    hora 6 h adelantada, y strftime ponía el día en inglés sin locale es_MX."""
    from app.services.appointment_booking_service import (
        _format_slot_time,
        format_spanish_date,
    )
    from app.services.availability_service import TZ

    local = appt.scheduled_at.astimezone(TZ)
    return format_spanish_date(local), _format_slot_time(local)


async def _push_reminder(db, appt, advertiser, title: str, body: str) -> bool:
    """Notificación web gratis si el cliente la activó en su portal. True si
    algún navegador la aceptó — entonces no hace falta el WhatsApp (cobrado)."""
    if not appt.contact_id:
        return False
    from app.services.portal_service import portal_url
    from app.services.web_push import push_to_contact

    try:
        accepted = await push_to_contact(
            db, appt.contact_id, title=title, body=body,
            url=portal_url(appt.contact_id), tag=f"appt-{appt.id}",
        )
    except Exception:
        logger.exception("[APPT] push reminder failed appt=%s — falling back to WhatsApp", appt.id)
        return False
    if accepted:
        logger.info("[APPT] Reminder sent by web push (free) appt=%s", appt.id)
    return accepted > 0


async def send_24h_reminders(db, now):
    """Send 24h appointment reminders."""
    from app.models.appointment import Appointment
    from app.models.contact import Contact
    from app.models.conversation import Conversation
    from app.models.user import User
    from app.services.meta_service import send_whatsapp, send_whatsapp_buttons
    from app.services.whatsapp_window import is_window_open

    window_24h_start = now + timedelta(hours=23)
    window_24h_end = now + timedelta(hours=25)

    result = await db.execute(
        select(Appointment).where(
            Appointment.reminder_24h_sent == False,
            Appointment.status.in_(["pending", "confirmed"]),
            Appointment.scheduled_at >= window_24h_start,
            Appointment.scheduled_at <= window_24h_end,
        )
    )
    for appt in result.scalars().all():
        user_result = await db.execute(select(User).where(User.id == appt.advertiser_id))
        advertiser = user_result.scalar_one_or_none()

        phone = appt.customer_phone
        if not phone and appt.contact_id:
            c_result = await db.execute(select(Contact).where(Contact.id == appt.contact_id))
            contact = c_result.scalar_one_or_none()
            if contact:
                phone = contact.phone

        pushed = False
        if advertiser:
            fecha, hora = _when(appt)
            # Sin awaiting_confirmation: eso es para el "responde 1/2" de
            # WhatsApp; la notificación lleva al portal, que tiene sus botones.
            pushed = await _push_reminder(
                db, appt, advertiser,
                title=f"Mañana: {appt.service}",
                body=f"{fecha.capitalize()} a las {hora} en {advertiser.business_name or 'tu cita'}. "
                     "Toca para confirmar o cancelar.",
            )

        if phone and advertiser and not pushed:
            contact_name = appt.customer_name.split()[0] if appt.customer_name else ""
            fecha, hora = _when(appt)
            biz_name = advertiser.business_name or "tu cita"
            msg = (
                f"📅 *Recordatorio de cita*\n\n"
                f"Hola {contact_name} 👋, tienes cita mañana:\n"
                f"📌 *{appt.service}*\n"
                f"🕐 {fecha} a las {hora}\n"
                f"🏪 {biz_name}\n\n"
                f"¿Puedes confirmar tu asistencia?\n"
                f"Responde *1* para confirmar ✅\n"
                f"Responde *2* para cancelar ❌"
            )
            window_open = False
            if appt.contact_id:
                conv_result = await db.execute(
                    select(Conversation).where(
                        Conversation.advertiser_id == advertiser.id,
                        Conversation.contact_id == appt.contact_id,
                        Conversation.status == "active",
                    )
                )
                window_open = is_window_open(conv_result.scalar_one_or_none())

            template_name = advertiser.meta_appointment_template_name
            sent = False
            if template_name:
                sid, err = await send_whatsapp_buttons(
                    to=phone,
                    body=msg,
                    template_name=template_name,
                    components=[{
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": contact_name},
                            {"type": "text", "text": appt.service},
                        ],
                    }],
                    advertiser=advertiser,
                )
                if sid:
                    sent = True
                elif window_open:
                    logger.warning("[APPT] Template send failed, falling back to text (window open): %s", err)
                    await send_whatsapp(phone, msg, advertiser=advertiser)
                    sent = True
                else:
                    logger.warning("[APPT] Template failed and window closed — skipping reminder for appt=%s", appt.id)
            elif window_open:
                await send_whatsapp(phone, msg, advertiser=advertiser)
                sent = True
            else:
                # No approved appointment template and the 24h window is
                # closed — hard block, no silent plain-text fallback.
                logger.warning("[APPT] No approved template and window closed — skipping 24h reminder for appt=%s", appt.id)

            if sent:
                appt.awaiting_confirmation = True
        elif phone and not advertiser:
            logger.warning("[APPT] Skipping 24h reminder for appt=%s — advertiser not found", appt.id)

        appt.reminder_24h_sent = True


async def send_1h_reminders(db, now):
    """Send 1h appointment reminders."""
    from app.models.appointment import Appointment
    from app.models.contact import Contact
    from app.models.user import User
    from app.services.meta_service import send_whatsapp

    window_1h_start = now + timedelta(minutes=50)
    window_1h_end = now + timedelta(minutes=70)

    result = await db.execute(
        select(Appointment).where(
            Appointment.reminder_1h_sent == False,
            Appointment.status.in_(["pending", "confirmed"]),
            Appointment.scheduled_at >= window_1h_start,
            Appointment.scheduled_at <= window_1h_end,
        )
    )
    for appt in result.scalars().all():
        user_result = await db.execute(select(User).where(User.id == appt.advertiser_id))
        advertiser = user_result.scalar_one_or_none()

        phone = appt.customer_phone
        if not phone and appt.contact_id:
            c_result = await db.execute(select(Contact).where(Contact.id == appt.contact_id))
            contact = c_result.scalar_one_or_none()
            if contact:
                phone = contact.phone

        if advertiser and await _push_reminder(
            db, appt, advertiser,
            title=f"Tu cita es en 1 hora: {appt.service}",
            body=f"A las {_when(appt)[1]} en {advertiser.business_name or 'tu cita'}. ¡Te esperamos!",
        ):
            appt.awaiting_confirmation = False
        elif phone and advertiser:
            hora = _when(appt)[1]
            biz_name = advertiser.business_name or "tu cita"
            status_emoji = "✅" if appt.status == "confirmed" else "📅"
            msg = (
                f"⏰ *Tu cita es en 1 hora*\n\n"
                f"{status_emoji} {appt.service} a las {hora}\n"
                f"🏪 {biz_name}\n\n"
                f"¡Te esperamos! 😊"
            )
            await send_whatsapp(phone, msg, advertiser=advertiser)
            appt.awaiting_confirmation = False
        elif phone and not advertiser:
            logger.warning("[APPT] Skipping 1h reminder for appt=%s — advertiser not found", appt.id)

        appt.reminder_1h_sent = True
