"""Agendamiento de autoservicio — compartido entre WhatsApp y el widget.

Ninguno de los dos canales tiene hoy agendamiento de autoservicio: el bot de
WhatsApp solo confirma/reagenda citas que el dueño ya creó a mano
(inbound_pipeline.py, sección "Appointment confirmation handler"). Esta es
funcionalidad nueva de cero, construida una sola vez aquí y conectada a ambos
canales sin tocar esa lógica existente — mismo patrón aditivo que
widget_order_service.py para pedidos.

Estado del agendamiento en curso vive en Redis (no en la tabla appointments),
para no requerir volver nullable a customer_name/service/scheduled_at en el
modelo Appointment ni tocar el dashboard de citas — el registro real en la
tabla solo se crea hasta que el flujo termina, ya con status="confirmed".

Pasos: collecting_date → collecting_time → collecting_name → (crea la cita).
"""
import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.user import User
from app.services.availability_service import TZ, get_available_slots
from app.services.claude_service import detect_appointment_intent
from app.services.owner_question_service import owner_number as get_owner_number
from app.services.portal_service import portal_footer

logger = logging.getLogger(__name__)

BOOKING_REDIS_PREFIX = "appt_booking:"
BOOKING_REDIS_TTL = 3600
MAX_SLOTS_SHOWN = 6

NEEDS_CONTACT_REPLY = (
    "¡Con gusto te ayudo a agendar! 📅 Para confirmar tu cita solo necesito tu "
    "nombre y tu WhatsApp — déjalos aquí abajo 👇"
)

_WEEKDAYS_ES = {
    "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3,
    "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}
_MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_DAY_MONTH_RE = re.compile(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)")
_NUMERIC_DATE_RE = re.compile(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$")

_WEEKDAY_NAMES_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MONTH_NAMES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def format_spanish_date(dt: datetime) -> str:
    """'%A %d de %B' equivalent that doesn't depend on the server's C locale
    (strftime's weekday/month names silently fall back to English when the
    es_MX locale isn't installed on the host)."""
    return f"{_WEEKDAY_NAMES_ES[dt.weekday()]} {dt.day} de {_MONTH_NAMES_ES[dt.month - 1]}"


def parse_spanish_date(text: str, today: date | None = None) -> date | None:
    """Lightweight Spanish date parser — no LLM call, $0 cost. Understands
    'hoy', 'mañana', 'pasado mañana', weekday names ('el viernes' → next
    Friday), 'DD de <mes>', and DD/MM(/YYYY)."""
    text = text.lower().strip()
    today = today or datetime.now(TZ).date()

    if text == "hoy":
        return today
    if text in ("mañana", "manana"):
        return today + timedelta(days=1)
    if text in ("pasado mañana", "pasado manana"):
        return today + timedelta(days=2)

    for name, weekday in _WEEKDAYS_ES.items():
        if name in text:
            days_ahead = (weekday - today.weekday()) % 7
            days_ahead = days_ahead or 7
            return today + timedelta(days=days_ahead)

    m = _DAY_MONTH_RE.search(text)
    if m:
        day_num, month_name = int(m.group(1)), m.group(2)
        month_num = _MONTHS_ES.get(month_name)
        if month_num and 1 <= day_num <= 31:
            try:
                d = date(today.year, month_num, day_num)
            except ValueError:
                return None
            return d if d >= today else date(today.year + 1, month_num, day_num)

    m2 = _NUMERIC_DATE_RE.match(text)
    if m2:
        day_num, month_num = int(m2.group(1)), int(m2.group(2))
        year = int(m2.group(3)) if m2.group(3) else today.year
        if year < 100:
            year += 2000
        try:
            d = date(year, month_num, day_num)
        except ValueError:
            return None
        if m2.group(3) is None and d < today:
            d = date(year + 1, month_num, day_num)
        return d

    return None


def _format_slot_time(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0").lower()


def _format_slots_page(all_slots: list[datetime], offset: int) -> tuple[list[datetime], str, bool]:
    """One page of up to MAX_SLOTS_SHOWN slots starting at *offset*, plus
    whether there are more beyond this page. Previously the bot silently
    truncated to the first MAX_SLOTS_SHOWN slots of the day and never showed
    the rest — a customer wanting an afternoon slot could never even see one
    was available. Paginating (instead of just raising the cap) keeps each
    WhatsApp message short and readable while still surfacing everything."""
    page = all_slots[offset:offset + MAX_SLOTS_SHOWN]
    options = "\n".join(f"{i}) {_format_slot_time(s)}" for i, s in enumerate(page, start=1))
    has_more = offset + MAX_SLOTS_SHOWN < len(all_slots)
    return page, options, has_more


QUICK_DAYS = 6
QUICK_DAYS_LOOKAHEAD = 14
_SHORT_WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


async def booking_quick_replies(db: AsyncSession, advertiser: User, contact: Contact | None, redis) -> list[dict]:
    """Botones para el paso actual de la cita (chat web: tocar en vez de
    escribir). Días: solo los que de verdad tienen horarios libres, con un
    valor que parse_spanish_date entiende sin ambigüedad (DD/MM). Nombre: el
    que ya conocemos. Los horarios ya salen como opciones numeradas."""
    if contact is None:
        return []
    state = await _load_state(redis, f"{BOOKING_REDIS_PREFIX}{advertiser.id}:{contact.id}")
    step = (state or {}).get("step")
    if step == "collecting_date":
        today = datetime.now(TZ).date()
        out: list[dict] = []
        for k in range(QUICK_DAYS_LOOKAHEAD):
            day = today + timedelta(days=k)
            if not await get_available_slots(db, advertiser, day):
                continue
            label = "Hoy" if k == 0 else "Mañana" if k == 1 else f"{_SHORT_WEEKDAYS[day.weekday()]} {day.day}"
            out.append({"label": label, "value": f"{day.day}/{day.month}/{day.year}"})
            if len(out) >= QUICK_DAYS:
                break
        return out
    if step == "collecting_name":
        name = (contact.name or "").strip()
        if name and not name.lstrip("+").replace(" ", "").isdigit():
            return [{"label": name, "value": name}]
    return []


async def _load_state(redis, key: str) -> dict | None:
    if not redis:
        return None
    raw = await redis.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def _save_state(redis, key: str, state: dict) -> None:
    if redis:
        await redis.setex(key, BOOKING_REDIS_TTL, json.dumps(state))


_GENERIC_WORDS = frozenset(
    ["quiero", "quisiera", "me", "gustaria", "gustaría", "puedo", "podria", "podría", "agendar", "agenda", "apartar", "reservar", "sacar", "hacer", "una", "un", "la", "el", "de", "del", "para", "por", "favor", "cita", "citas", "visita", "visitar", "turno", "hora", "reservacion", "reservación", "programar", "pedir", "solicitar", "necesito", "hola", "buenas", "buenos", "dias", "días", "tardes", "noches", "si", "sí", "ok"]
)


def service_label(message: str) -> str:
    """Qué se agenda, legible. "quiero agendar una cita para corte de cabello"
    → se queda tal cual (dice el servicio); "quiero una cita" → "Cita" (antes
    la confirmación decía "📌 quiero una cita")."""
    text = " ".join((message or "").split())[:120]
    words = [w.strip("¿?¡!.,;:") for w in text.lower().split()]
    if not [w for w in words if w and w not in _GENERIC_WORDS]:
        return "Cita"
    return text[:1].upper() + text[1:]


async def handle_appointment_booking(
    db: AsyncSession, advertiser: User, contact: Contact | None, message: str, redis,
    channel: str = "whatsapp",
) -> str | None:
    """Returns a reply to send instead of the RAG bot / order flow, or None if
    this message isn't appointment-related and the caller should fall through.
    *redis* is the caller's own client (each channel already resolves one) —
    passed in rather than fetched here so both channels share one connection
    and the booking state is trivially mockable in tests. *channel* is
    "whatsapp" or "widget" — only used to label the owner notification
    correctly, since this flow is shared between both."""
    key = f"{BOOKING_REDIS_PREFIX}{advertiser.id}:{contact.id}" if contact else None

    state = await _load_state(redis, key) if key else None
    if state:
        return await _advance(db, redis, key, advertiser, contact, state, message, channel)

    if not detect_appointment_intent(message):
        return None

    if not contact:
        return NEEDS_CONTACT_REPLY

    state = {"step": "collecting_date", "service": service_label(message)}
    await _save_state(redis, key, state)
    if channel == "widget":
        # En el chat web los días salen como botones (booking_quick_replies).
        return "¡Con gusto! 📅 ¿Qué día te gustaría tu cita? Elige un día 👇 o escríbelo."
    return (
        "¡Con gusto! 📅 ¿Qué día te gustaría tu cita?\n"
        "Puedes escribir por ejemplo *hoy*, *mañana*, *el viernes*, o *15 de agosto*."
    )


async def _advance(
    db: AsyncSession, redis, key: str, advertiser: User, contact: Contact, state: dict, message: str,
    channel: str = "whatsapp",
) -> str:
    step = state.get("step")

    if step == "collecting_date":
        parsed = parse_spanish_date(message)
        if not parsed:
            return (
                "No entendí bien la fecha 🤔 Intenta con algo como *hoy*, *mañana*, "
                "*el viernes*, o *15 de agosto*."
            )
        slots = await get_available_slots(db, advertiser, parsed)
        if not slots:
            return "No tenemos horarios disponibles ese día 😕 ¿Quieres intentar con otra fecha?"

        _, options, has_more = _format_slots_page(slots, 0)
        state["step"] = "collecting_time"
        state["day"] = parsed.isoformat()
        state["offset"] = 0
        await _save_state(redis, key, state)
        more_hint = "\n\nEscribe *MAS* para ver más horarios." if has_more else ""
        return f"Estos son los horarios disponibles:\n{options}\n\nResponde con el número de la opción que prefieras.{more_hint}"

    if step == "collecting_time":
        day = date.fromisoformat(state["day"])
        all_slots = await get_available_slots(db, advertiser, day)
        offset = state.get("offset", 0)
        choice = message.strip().lower()

        if choice in ("mas", "más", "more"):
            next_offset = offset + MAX_SLOTS_SHOWN
            new_offset = next_offset if next_offset < len(all_slots) else 0
            state["offset"] = new_offset
            await _save_state(redis, key, state)
            page, options, has_more = _format_slots_page(all_slots, new_offset)
            if not page:
                return "Ese día ya no tiene horarios disponibles 😕 ¿Quieres intentar con otra fecha?"
            more_hint = "\n\nEscribe *MAS* para ver más horarios." if has_more else ""
            wrap_note = " (de nuevo desde el inicio)" if new_offset == 0 and offset != 0 else ""
            return f"Horarios disponibles{wrap_note}:\n{options}\n\nResponde con el número de la opción que prefieras.{more_hint}"

        page, options, has_more = _format_slots_page(all_slots, offset)
        if not choice.isdigit() or not (1 <= int(choice) <= len(page)):
            if not page:
                return "Ese horario ya no está disponible 😕 ¿Quieres intentar con otra fecha?"
            more_hint = "\n\nEscribe *MAS* para ver más horarios." if has_more else ""
            return f"Elige un número válido de la lista:\n{options}{more_hint}"

        chosen = page[int(choice) - 1]
        state["step"] = "collecting_name"
        state["chosen_slot"] = chosen.isoformat()
        await _save_state(redis, key, state)
        return "Perfecto 👍 ¿A qué nombre confirmamos la cita?"

    # step == "collecting_name" — the only remaining transition
    customer_name = message.strip()
    chosen_slot = datetime.fromisoformat(state["chosen_slot"])

    # Entre que eligió la hora y dio su nombre, otro cliente (por web o por
    # WhatsApp) pudo apartarla. Se revisa otra vez, con un candado por negocio
    # para que dos confirmaciones al mismo tiempo no se crucen (vale hasta el commit).
    from sqlalchemy import text as _sql

    from app.domain.appointment_actions import (
        AppointmentConflictError,
        check_no_conflict,
    )

    await db.execute(_sql("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"appointments:{advertiser.id}"})
    try:
        await check_no_conflict(db, advertiser, chosen_slot, 30)
    except AppointmentConflictError:
        day = chosen_slot.astimezone(TZ).date()
        slots = await get_available_slots(db, advertiser, day)
        if not slots:
            if redis:
                await redis.delete(key)
            return "Uy, ese horario se acaba de ocupar 😕 y ya no quedan más ese día. ¿Quieres intentar con otra fecha?"
        _, options, has_more = _format_slots_page(slots, 0)
        state.update({"step": "collecting_time", "day": day.isoformat(), "offset": 0})
        state.pop("chosen_slot", None)
        await _save_state(redis, key, state)
        more_hint = "\n\nEscribe *MAS* para ver más horarios." if has_more else ""
        return (
            f"Uy, ese horario se acaba de ocupar 😕 Estos siguen libres:\n{options}\n\n"
            f"Responde con el número de la opción que prefieras.{more_hint}"
        )

    appointment = Appointment(
        advertiser_id=advertiser.id,
        contact_id=contact.id,
        customer_name=customer_name,
        customer_phone=contact.phone,
        service=state["service"],
        scheduled_at=chosen_slot,
        duration_min=30,
        status="confirmed",
    )
    db.add(appointment)

    if advertiser.google_calendar_connected and advertiser.google_refresh_token:
        try:
            from app.services.calendar_service import create_event

            event_id = create_event(
                refresh_token=advertiser.google_refresh_token,
                summary=f"📅 {appointment.service} — {customer_name}",
                description=f"Cliente: {customer_name}\nTeléfono: {contact.phone}",
                start_dt=chosen_slot,
                duration_min=30,
                customer_phone=contact.phone,
            )
            appointment.google_event_id = event_id
        except Exception as e:
            logger.warning("[APPT-BOOKING] Google Calendar sync failed: %s", e)

    await db.commit()

    if redis:
        await redis.delete(key)

    await _notify_owner(advertiser, appointment, channel)

    fecha = format_spanish_date(chosen_slot)
    hora = _format_slot_time(chosen_slot)
    return (
        f"✅ *¡Cita confirmada!*\n\n"
        f"📌 {appointment.service}\n"
        f"🕐 {fecha} a las {hora}\n\n"
        "¡Te esperamos! Si necesitas reagendar, escríbenos."
        # El link a su portal solo por WhatsApp: en el chat web ya está ahí.
        f"{portal_footer(contact.id) if channel == 'whatsapp' else ''}"
    )


async def _notify_owner(advertiser: User, appointment: Appointment, channel: str = "whatsapp") -> None:
    from app.core.email import send_new_appointment_email

    fecha = format_spanish_date(appointment.scheduled_at.astimezone(TZ))
    hora = _format_slot_time(appointment.scheduled_at.astimezone(TZ))

    asyncio.create_task(
        send_new_appointment_email(
            to=advertiser.email,
            business_name=advertiser.business_name or "Tu negocio",
            service=appointment.service,
            customer_name=appointment.customer_name,
            customer_phone=appointment.customer_phone or "",
            fecha=fecha,
            hora=hora,
        )
    )

    if get_owner_number(advertiser):
        from app.services.meta_service import send_whatsapp

        owner_number = get_owner_number(advertiser)
        origen = "desde tu página web" if channel == "widget" else "desde WhatsApp"
        wa_notify = (
            f"📅 *NUEVA CITA* ({origen})\n"
            f"────────────────\n"
            f"📌 {appointment.service}\n"
            f"👤 Cliente: {appointment.customer_name}\n"
            f"📱 Teléfono: {appointment.customer_phone}\n"
            f"🕐 {fecha} a las {hora}\n"
            f"────────────────"
        )
        try:
            await send_whatsapp(owner_number, wa_notify, advertiser=advertiser)
        except Exception:
            logger.warning("[APPT-BOOKING] Failed to notify owner via WhatsApp", exc_info=True)
