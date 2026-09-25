"""Chequeo de conflicto de horario para citas — única fuente de verdad,
compartida entre el endpoint REST (dashboard) y el Copiloto (chat CRM).

El flujo de autoservicio (WhatsApp/widget, appointment_booking_service.py)
ya evita conflictos por construcción: solo ofrece horarios que
get_available_slots() generó segundos antes, así que no necesita este
chequeo.

REST y Copiloto sí dejan que el dueño elija cualquier horario — es su propio
calendario, puede tener razones legítimas para agendar fuera del
business_hours configurado (ej. un cliente que llamó fuera de horario).
Lo que ninguno de los dos validaba es que esa misma cita se creara dos veces
en el mismo horario (doble-booking) — ese es el bug real que comparten y que
esta función cierra.
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.user import User
from app.services.availability_service import TZ


class AppointmentConflictError(Exception):
    """El horario pedido se cruza con una cita ya existente (no cancelada)."""


async def check_no_conflict(
    db: AsyncSession,
    advertiser: User,
    scheduled_at: datetime,
    duration_min: int = 30,
    exclude_appointment_id=None,
) -> None:
    """Lanza AppointmentConflictError si [scheduled_at, scheduled_at +
    duration_min) se cruza con otra cita no cancelada del mismo anunciante.
    *exclude_appointment_id* permite validar una edición sin chocar consigo
    misma."""
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=TZ)
    slot_end = scheduled_at + timedelta(minutes=duration_min)

    q = select(Appointment).where(
        Appointment.advertiser_id == advertiser.id,
        Appointment.status != "cancelled",
    )
    if exclude_appointment_id is not None:
        q = q.where(Appointment.id != exclude_appointment_id)

    result = await db.execute(q)
    for existing in result.scalars().all():
        existing_start = existing.scheduled_at
        existing_end = existing_start + timedelta(minutes=existing.duration_min)
        if scheduled_at < existing_end and slot_end > existing_start:
            raise AppointmentConflictError(
                f"Ya tienes una cita agendada de "
                f"{existing_start.astimezone(TZ).strftime('%H:%M')} a "
                f"{existing_end.astimezone(TZ).strftime('%H:%M')} el "
                f"{existing_start.astimezone(TZ).strftime('%d/%m/%Y')} — elige otro horario."
            )
