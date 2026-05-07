"""
Servicio de cupones — generación, formato y validación.
"""
import secrets
import string
from datetime import datetime, timezone, timedelta


def generate_coupon_code(length: int = 8) -> str:
    """Genera un código de cupón único alfanumérico en mayúsculas."""
    chars = string.ascii_uppercase + string.digits
    # Evitar caracteres confusos (0/O, 1/I/L)
    chars = chars.replace("0", "").replace("O", "").replace("1", "").replace("I", "").replace("L", "")
    return "".join(secrets.choice(chars) for _ in range(length))


def format_coupon_in_message(
    message: str,
    code: str,
    expires_at: datetime,
    description: str = "",
) -> str:
    """
    Embebe el cupón al final del mensaje con formato de radio.

    Ejemplo:
        🎫 Tu cupón exclusivo: *AR7X9K2P*
        📅 Válido hasta: 07/05 23:59
        ↩️ Responde CANJEAR para activarlo
    """
    expiry_str = expires_at.strftime("%d/%m %H:%M")
    coupon_block = f"\n\n🎫 Tu cupón: *{code}*"
    if description:
        coupon_block += f"\n✨ {description}"
    coupon_block += f"\n⏰ Válido hasta: {expiry_str}"
    coupon_block += "\n↩️ Responde *CANJEAR* para activarlo"
    return message + coupon_block


def default_expiry(hours: int = 72) -> datetime:
    """Expiración por defecto: 72 horas desde ahora."""
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def is_expired(expires_at: datetime) -> bool:
    return datetime.now(timezone.utc) > expires_at


REDEEM_KEYWORDS = {"canjear", "canjealo", "quiero", "lo quiero", "activar", "aplicar"}


def is_redeem_intent(text: str) -> bool:
    """Detecta si el mensaje del usuario intenta canjear un cupón."""
    clean = text.lower().strip()
    return any(kw in clean for kw in REDEEM_KEYWORDS)
