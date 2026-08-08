"""Disponibilidad de citas — slots libres = business_hours menos Appointments
ya existentes. Consulta local a la tabla appointments; SIN integración en
tiempo real con Google Calendar freebusy (esa API no existe hoy en
calendar_service.py, agregarla sería una ampliación de alcance real) — mejora
V2 si el negocio agenda cosas fuera de AdRadio que deban bloquear horarios.
"""
import zoneinfo
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.user import User

TZ = zoneinfo.ZoneInfo("America/Mexico_City")
SLOT_STEP_MINUTES = 30
_WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

DEFAULT_BUSINESS_HOURS: dict[str, list[str] | None] = {
    "mon": ["09:00", "18:00"],
    "tue": ["09:00", "18:00"],
    "wed": ["09:00", "18:00"],
    "thu": ["09:00", "18:00"],
    "fri": ["09:00", "18:00"],
    "sat": ["09:00", "14:00"],
    "sun": None,
}


def _parse_hm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


async def get_available_slots(
    db: AsyncSession, advertiser: User, day: date, duration_min: int = 30
) -> list[datetime]:
    """Free start datetimes (tz-aware, America/Mexico_City) on *day*, each
    duration_min long, given the advertiser's business_hours and existing
    non-cancelled Appointments. Past times on the current day are excluded."""
    hours = advertiser.business_hours or DEFAULT_BUSINESS_HOURS
    day_hours = hours.get(_WEEKDAY_KEYS[day.weekday()])
    if not day_hours:
        return []

    day_start = datetime.combine(day, _parse_hm(day_hours[0]), tzinfo=TZ)
    day_end = datetime.combine(day, _parse_hm(day_hours[1]), tzinfo=TZ)

    result = await db.execute(
        select(Appointment).where(
            Appointment.advertiser_id == advertiser.id,
            Appointment.status != "cancelled",
            Appointment.scheduled_at >= day_start,
            Appointment.scheduled_at < day_end,
        )
    )
    busy = [
        (a.scheduled_at.astimezone(TZ), a.scheduled_at.astimezone(TZ) + timedelta(minutes=a.duration_min))
        for a in result.scalars().all()
    ]

    now = datetime.now(TZ)
    slots: list[datetime] = []
    cursor = day_start
    step = timedelta(minutes=SLOT_STEP_MINUTES)
    duration = timedelta(minutes=duration_min)
    while cursor + duration <= day_end:
        slot_end = cursor + duration
        if cursor > now and not any(cursor < b_end and slot_end > b_start for b_start, b_end in busy):
            slots.append(cursor)
        cursor += step
    return slots
