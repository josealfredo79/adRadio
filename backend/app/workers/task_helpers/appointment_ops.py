"""
Appointment reminder operations.
"""
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

logger = logging.getLogger(__name__)


async def send_24h_reminders(db, now):
    """Send 24h appointment reminders."""
    from app.models.appointment import Appointment
    from app.models.user import User
    from app.models.contact import Contact
    from app.services.twilio_service import send_whatsapp, send_whatsapp_buttons
    from app.config import settings

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
        from_number = advertiser.whatsapp_number if advertiser else None

        phone = appt.customer_phone
        if not phone and appt.contact_id:
            c_result = await db.execute(select(Contact).where(Contact.id == appt.contact_id))
            contact = c_result.scalar_one_or_none()
            if contact:
                phone = contact.phone

        if phone:
            contact_name = appt.customer_name.split()[0] if appt.customer_name else ""
            hora = appt.scheduled_at.strftime("%I:%M %p").lstrip("0")
            fecha = appt.scheduled_at.strftime("%A %d de %B")
            biz_name = advertiser.business_name if advertiser else "tu cita"
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
            button_sid = settings.TWILIO_APPOINTMENT_CONFIRM_BUTTONS_SID
            if button_sid:
                sid, err = await send_whatsapp_buttons(
                    to=phone,
                    body=msg,
                    template_sid=button_sid,
                    variables={"1": contact_name, "2": appt.service},
                    from_number=from_number,
                )
                if not sid:
                    logger.warning("[APPT] Button template failed, falling back to text: %s", err)
                    await send_whatsapp(phone, msg, from_number=from_number)
            else:
                await send_whatsapp(phone, msg, from_number=from_number)
            appt.awaiting_confirmation = True

        appt.reminder_24h_sent = True


async def send_1h_reminders(db, now):
    """Send 1h appointment reminders."""
    from app.models.appointment import Appointment
    from app.models.user import User
    from app.models.contact import Contact
    from app.services.twilio_service import send_whatsapp

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
        from_number = advertiser.whatsapp_number if advertiser else None

        phone = appt.customer_phone
        if not phone and appt.contact_id:
            c_result = await db.execute(select(Contact).where(Contact.id == appt.contact_id))
            contact = c_result.scalar_one_or_none()
            if contact:
                phone = contact.phone

        if phone:
            hora = appt.scheduled_at.strftime("%I:%M %p").lstrip("0")
            biz_name = advertiser.business_name if advertiser else "tu cita"
            status_emoji = "✅" if appt.status == "confirmed" else "📅"
            msg = (
                f"⏰ *Tu cita es en 1 hora*\n\n"
                f"{status_emoji} {appt.service} a las {hora}\n"
                f"🏪 {biz_name}\n\n"
                f"¡Te esperamos! 😊"
            )
            await send_whatsapp(phone, msg, from_number=from_number)
            appt.awaiting_confirmation = False

        appt.reminder_1h_sent = True
