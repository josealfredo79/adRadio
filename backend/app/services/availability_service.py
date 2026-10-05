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


def _norm(text: str | None) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", (text or "").lower())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())


def staff_names(advertiser: User) -> list[str]:
    """El personal que atiende citas (users.staff); vacío = el negocio no lo usa."""
    return [s["name"] for s in (advertiser.staff or []) if isinstance(s, dict) and s.get("name")]


def staff_for(advertiser: User, service: str | None = None, staff: str | None = None) -> list[str]:
    """Quiénes pueden atender: la persona pedida (si existe) o todos los que
    hacen ese servicio (lista de servicios vacía = hace todo)."""
    people = [s for s in (advertiser.staff or []) if isinstance(s, dict) and s.get("name")]
    if staff:
        wanted = _norm(staff)
        people = [p for p in people if _norm(p["name"]) == wanted or wanted in _norm(p["name"]).split()]
    if service:
        wanted = _norm(service)
        people = [p for p in people
                  if not p.get("services") or any(_norm(x) == wanted or wanted in _norm(x) or _norm(x) in wanted
                                                  for x in p["services"])]
    return [p["name"] for p in people]


def free_staff(
    busy: list[tuple[datetime, datetime, str | None]],
    start: datetime,
    end: datetime,
    candidates: list[str],
    everyone: list[str],
) -> list[str]:
    """De *candidates*, quiénes están libres en [start, end). Una cita sin
    persona asignada (la agendó el bot de WhatsApp o el dueño sin elegir)
    ocupa a alguien: cuenta contra el cupo total de personas libres."""
    overlapping = [(s, e, who) for s, e, who in busy if start < e and end > s]
    taken = {who for _, _, who in overlapping if who in everyone}
    unassigned = sum(1 for _, _, who in overlapping if who not in everyone)
    if len([p for p in everyone if p not in taken]) - unassigned <= 0:
        return []
    return [p for p in candidates if p not in taken]


async def _busy(db: AsyncSession, advertiser: User, day_start: datetime, day_end: datetime, exclude_id=None):
    q = select(Appointment).where(
        Appointment.advertiser_id == advertiser.id,
        Appointment.status != "cancelled",
        Appointment.scheduled_at >= day_start - timedelta(hours=12),
        Appointment.scheduled_at < day_end,
    )
    if exclude_id is not None:
        q = q.where(Appointment.id != exclude_id)
    return [
        (a.scheduled_at.astimezone(TZ), a.scheduled_at.astimezone(TZ) + timedelta(minutes=a.duration_min), a.staff_name)
        for a in (await db.execute(q)).scalars().all()
    ]


async def available_staff(
    db: AsyncSession, advertiser: User, start: datetime, duration_min: int = 30,
    service: str | None = None, staff: str | None = None, exclude_id=None,
) -> list[str] | None:
    """Quiénes pueden tomar esa cita a esa hora. None = el negocio no tiene
    personal dado de alta (cupo de una cita a la vez, como siempre)."""
    everyone = staff_names(advertiser)
    if not everyone:
        return None
    start = start.astimezone(TZ) if start.tzinfo else start.replace(tzinfo=TZ)
    end = start + timedelta(minutes=duration_min)
    busy = await _busy(db, advertiser, start, end, exclude_id)
    return free_staff(busy, start, end, staff_for(advertiser, service, staff), everyone)


async def get_available_slots(
    db: AsyncSession, advertiser: User, day: date, duration_min: int = 30,
    service: str | None = None, staff: str | None = None,
) -> list[datetime]:
    """Free start datetimes (tz-aware, America/Mexico_City) on *day*, each
    duration_min long, given the advertiser's business_hours and existing
    non-cancelled Appointments. Past times on the current day are excluded.

    Con personal (users.staff): un horario está libre si alguien que haga ese
    servicio (o la persona pedida) está libre — con 3 estilistas caben 3
    citas a la misma hora."""
    hours = advertiser.business_hours or DEFAULT_BUSINESS_HOURS
    day_hours = hours.get(_WEEKDAY_KEYS[day.weekday()])
    if not day_hours:
        return []

    day_start = datetime.combine(day, _parse_hm(day_hours[0]), tzinfo=TZ)
    day_end = datetime.combine(day, _parse_hm(day_hours[1]), tzinfo=TZ)
    busy = await _busy(db, advertiser, day_start, day_end)
    everyone = staff_names(advertiser)
    candidates = staff_for(advertiser, service, staff) if everyone else []

    now = datetime.now(TZ)
    slots: list[datetime] = []
    cursor = day_start
    step = timedelta(minutes=SLOT_STEP_MINUTES)
    duration = timedelta(minutes=duration_min)
    while cursor + duration <= day_end:
        slot_end = cursor + duration
        if cursor > now:
            if everyone:
                free = bool(free_staff(busy, cursor, slot_end, candidates, everyone))
            else:
                free = not any(cursor < b_end and slot_end > b_start for b_start, b_end, _ in busy)
            if free:
                slots.append(cursor)
        cursor += step
    return slots
