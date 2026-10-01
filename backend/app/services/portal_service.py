"""Portal del cliente — el link personal que saca la conversación de WhatsApp
(cobrada por Meta desde 2026-10-01, incluso los mensajes de servicio) hacia la
web (gratis): un solo mensaje con /c/{token} y el cliente ve sus citas,
pedidos y cupones, cancela una cita o sigue platicando con el bot, sin más
mensajes de WhatsApp de por medio.

El token no se guarda en BD: es el id del contacto + una firma HMAC con
SECRET_KEY. Quien tiene el link es quien recibió el WhatsApp — el mismo
modelo de confianza que un link de seguimiento de paquetería. Rotar
SECRET_KEY invalida todos los links (aceptable: el bot manda uno nuevo en la
siguiente confirmación).
"""
import base64
import hashlib
import hmac
import uuid

from app.config import settings

# Separa estas firmas de cualquier otro HMAC hecho con la misma SECRET_KEY
# (ej. el state de OAuth de Google Calendar en appointments.py), para que una
# firma de un lado nunca valga del otro.
_DOMAIN = b"customer-portal:v1:"
_SIG_BYTES = 12


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(contact_id: uuid.UUID) -> bytes:
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, _DOMAIN + contact_id.bytes, hashlib.sha256).digest()[:_SIG_BYTES]


def make_portal_token(contact_id: uuid.UUID) -> str:
    return f"{_b64(contact_id.bytes)}.{_b64(_sign(contact_id))}"


def read_portal_token(token: str) -> uuid.UUID | None:
    """El contact_id del token, o None si está mal formado o la firma no
    cuadra. Nunca lanza — el endpoint público responde 404 igual en todos los
    casos para no dar pistas de qué parte falló."""
    if not settings.SECRET_KEY:
        return None
    try:
        id_part, sig_part = token.split(".", 1)
        contact_id = uuid.UUID(bytes=_unb64(id_part))
        sig = _unb64(sig_part)
    except (ValueError, TypeError):
        return None
    if not hmac.compare_digest(sig, _sign(contact_id)):
        return None
    return contact_id


def portal_url(contact_id: uuid.UUID) -> str:
    base = (settings.FRONTEND_URL or "https://www.iaradio.online").rstrip("/")
    return f"{base}/c/{make_portal_token(contact_id)}"


def portal_footer(contact_id: uuid.UUID | None) -> str:
    """Línea que se agrega al final de las confirmaciones de cita/pedido.
    Vacía sin contacto (ej. widget anónimo) o sin SECRET_KEY (dev/tests sin
    configurar), para que las confirmaciones nunca lleven un link roto."""
    if contact_id is None or not settings.SECRET_KEY:
        return ""
    return f"\n\n📲 Tus citas, pedidos y cupones, aquí: {portal_url(contact_id)}"


def promo_url(contact_id: uuid.UUID, campaign_id: uuid.UUID) -> str:
    return f"{portal_url(contact_id)}/promo/{campaign_id}"


def promo_footer(contact_id: uuid.UUID | None, campaign_id: uuid.UUID | None) -> str:
    """Línea para el texto de una campaña (pie del banner, o el texto que ya
    acompaña a la nota de voz) — va en el mismo mensaje, no cuesta uno extra.
    Vacía en los mismos casos que portal_footer."""
    if contact_id is None or campaign_id is None or not settings.SECRET_KEY:
        return ""
    return f"\n\n👉 Ve la promo completa y apártala aquí: {promo_url(contact_id, campaign_id)}"
