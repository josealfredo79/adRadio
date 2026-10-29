"""
Channel-agnostic outbound pacing helpers (used by campaign/appointment jobs
to stay under WhatsApp rate limits regardless of which API sends the message).
"""
import random
from datetime import datetime, timedelta, timezone


def anti_ban_delay() -> int:
    """Return a human-paced random delay in seconds to stay under WhatsApp rate limits.

    Strategy:
    - 70% of the time: 45-90s (normal human typing pace)
    - 20% of the time: 90-180s (longer pause, feels more natural)
    - 10% of the time: 180-300s (extra-long gap to break patterns)
    This keeps us well under 60 msgs/hour on average.
    """
    roll = random.random()
    if roll < 0.70:
        return random.randint(45, 90)
    elif roll < 0.90:
        return random.randint(90, 180)
    else:
        return random.randint(180, 300)


_HUMAN_HOUR_START = 8
_HUMAN_HOUR_END = 21
_BLOCKED_WEEKDAY = 6  # datetime.weekday(): Monday=0 ... Sunday=6


def _is_human_hour_at(now_local: datetime) -> bool:
    if now_local.weekday() == _BLOCKED_WEEKDAY:
        return False
    return _HUMAN_HOUR_START <= now_local.hour < _HUMAN_HOUR_END


def _next_human_hour_after(now_local: datetime) -> datetime:
    candidate = now_local.replace(hour=_HUMAN_HOUR_START, minute=0, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    while candidate.weekday() == _BLOCKED_WEEKDAY:
        candidate += timedelta(days=1)
    return candidate


_WEEKDAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def send_starts_label(timezone_offset: int = -6, now_local: datetime | None = None) -> str | None:
    """Cuándo sale una campaña mandada ahora: None si sale ya; si no (de
    noche o en domingo espera al horario humano), "mañana a las 8:00 a. m.".
    Para que el dueño no lea "enviada" cuando sale hasta mañana (prueba real
    2026-10-28)."""
    tz = timezone(timedelta(hours=timezone_offset))
    now_local = now_local or datetime.now(tz)
    if _is_human_hour_at(now_local):
        return None
    at = _next_human_hour_after(now_local)
    days = (at.date() - now_local.date()).days
    when = "hoy" if days == 0 else "mañana" if days == 1 else f"el {_WEEKDAYS_ES[at.weekday()]}"
    hour = at.hour % 12 or 12
    return f"{when} a las {hour}:{at.minute:02d} {'a. m.' if at.hour < 12 else 'p. m.'}"


def is_human_hour(timezone_offset: int = -6) -> bool:
    """Check if current time is within human sending hours: Mon-Sat,
    8am-9pm in given UTC offset. Sunday is blocked outright regardless of
    the hour (Capa 14 anti-baneo) — a WhatsApp marketing send landing on a
    day most businesses aren't expected to be operating is exactly the kind
    of pattern that draws spam reports."""
    tz = timezone(timedelta(hours=timezone_offset))
    return _is_human_hour_at(datetime.now(tz))


def next_human_hour_utc(timezone_offset: int = -6) -> datetime:
    """The next UTC instant is_human_hour() will return True, starting from
    now. Centralizes the reschedule math (instead of duplicating the
    8am-9pm/Sunday rules ad-hoc at each call site) so the two can't drift
    out of sync — that drift is exactly what happened before Capa 14, when
    schedule_campaign's hand-rolled reschedule calc didn't know about
    Sunday at all."""
    tz = timezone(timedelta(hours=timezone_offset))
    now_local = datetime.now(tz)
    return _next_human_hour_after(now_local).astimezone(timezone.utc)
