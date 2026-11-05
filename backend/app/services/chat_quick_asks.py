"""Botones para arrancar el chat web con un toque (AgentChat).

Los de siempre ("¿Qué productos tienen?", "Quiero agendar una cita"…) los pone
el frontend. La cuenta de IaRadio no es un negocio con clientes: su chat es el
de ventas de IaRadio, y ahí esos botones confundían a los interesados.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.product import Product
from app.models.user import User

# La cuenta que vende IaRadio (también guarda los planes como productos, ver
# chat_demo.py).
IARADIO_ACCOUNT_EMAIL = "tecnologicotlaxiaco@gmail.com"

SALES_QUICK_ASKS = [
    # "onboard": el chat no se lo manda al bot, abre el alta ahí mismo
    # (frontend: OnboardingFlow; backend: onboarding.py + owner_whatsapp_auth.py).
    {"icon": "✨", "text": "Quiero probarlo gratis", "action": "onboard"},
    {"icon": "🤖", "text": "¿Qué hace IaRadio?"},
    {"icon": "🏪", "text": "¿Sirve para mi negocio?"},
    {"icon": "💲", "text": "¿Cuánto cuesta?"},
]


def chat_quick_asks(user: User) -> list[dict] | None:
    """None = los botones de siempre (los decide el frontend)."""
    if (user.email or "").lower() == IARADIO_ACCOUNT_EMAIL:
        return SALES_QUICK_ASKS
    return None


# Giros que viven de citas aunque el dueño no haya llenado sus servicios.
_BOOKING_WORDS = (
    "estetic", "estétic", "salon", "salón", "barber", "uñas", "spa", "belleza", "consultorio", "doctor",
    "medic", "médic", "dental", "dentist", "clinica", "clínica", "veterin", "psicolog", "nutri",
    "fisio", "masaj", "tatu", "abogad", "notar", "taller", "clases", "academ",
)

ASK_PRODUCTS = {"icon": "🛍️", "text": "¿Qué productos tienen?"}
ASK_HOURS = {"icon": "🕒", "text": "¿Cuál es su horario?"}
ASK_APPOINTMENT = {"icon": "📅", "text": "Quiero agendar una cita"}
ASK_ORDER = {"icon": "🛒", "text": "Quiero hacer un pedido"}
ASK_DELIVERY = {"icon": "🛵", "text": "¿Hacen entregas a domicilio?"}
ASK_WHERE = {"icon": "📍", "text": "¿Dónde están?"}


def _last10(number: str | None) -> str:
    return "".join(ch for ch in (number or "") if ch.isdigit())[-10:]


async def _has_real_appointment(db: AsyncSession, user: User) -> bool:
    """¿Algún cliente ya le sacó cita de verdad? No cuentan las canceladas, las
    de "Cita general" (lo que queda cuando el negocio no tiene servicios) ni las
    que hizo el propio dueño probando: CityCell, una tienda de celulares, tenía
    3 así y seguía mostrando "agendar una cita" (2026-11-04)."""
    from app.services.owner_question_service import owner_number

    rows = (await db.execute(
        select(Appointment.service, Appointment.customer_phone)
        .where(Appointment.advertiser_id == user.id, Appointment.status != "cancelled")
        .order_by(Appointment.created_at.desc())
        .limit(20)
    )).all()
    owner = _last10(owner_number(user))
    for service, phone in rows:
        name = (service or "").strip().lower()
        if not name or name in ("cita", "cita general"):
            continue
        if owner and _last10(phone) == owner:
            continue
        return True
    return False


async def chat_quick_asks_for(db: AsyncSession, user: User) -> list[dict]:
    """Los botones de arranque que le sirven a ESTE negocio: "agendar una
    cita" solo si da citas y "hacer un pedido" solo si tiene productos (una
    tienda de celulares mostraba "agendar una cita", prueba CityCell 2026-11-04)."""
    sales = chat_quick_asks(user)
    if sales:
        return sales
    has_products = await db.scalar(
        select(Product.id).where(Product.advertiser_id == user.id, Product.active.is_(True)).limit(1)
    ) is not None
    category = (user.business_category or "").lower()
    takes_appointments = bool(user.appointment_services) or any(w in category for w in _BOOKING_WORDS)
    if not takes_appointments:
        takes_appointments = await _has_real_appointment(db, user)
    asks = [ASK_PRODUCTS, ASK_HOURS]
    if takes_appointments:
        asks.append(ASK_APPOINTMENT)
    if has_products:
        asks.append(ASK_ORDER)
    for extra in ([ASK_DELIVERY] if user.delivers_home else []) + [ASK_WHERE]:
        if len(asks) < 4:
            asks.append(extra)
    return asks
