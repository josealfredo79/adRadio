"""Botones para arrancar el chat web con un toque (AgentChat).

Los de siempre ("¿Qué productos tienen?", "Quiero agendar una cita"…) los pone
el frontend. La cuenta de IaRadio no es un negocio con clientes: su chat es el
de ventas de IaRadio, y ahí esos botones confundían a los interesados.
"""
from app.models.user import User

# La cuenta que vende IaRadio (también guarda los planes como productos, ver
# chat_demo.py).
IARADIO_ACCOUNT_EMAIL = "tecnologicotlaxiaco@gmail.com"

SALES_QUICK_ASKS = [
    {"icon": "✨", "text": "Quiero probarlo gratis"},
    {"icon": "🤖", "text": "¿Qué hace IaRadio?"},
    {"icon": "🏪", "text": "¿Sirve para mi negocio?"},
    {"icon": "💲", "text": "¿Cuánto cuesta?"},
]


def chat_quick_asks(user: User) -> list[dict] | None:
    """None = los botones de siempre (los decide el frontend)."""
    if (user.email or "").lower() == IARADIO_ACCOUNT_EMAIL:
        return SALES_QUICK_ASKS
    return None
