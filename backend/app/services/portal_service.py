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
import logging
import uuid

from app.config import settings

logger = logging.getLogger(__name__)

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


# ─── Invitación a seguir la plática en la web ────────────────────────────────
# En la plática normal (precios, catálogo, horario) es donde más mensajes de
# WhatsApp se gastan, y ahí el link no salía nunca. Una vez al día por
# cliente, al final de una respuesta del bot (mismo mensaje, sin costo extra):
# en su 3er mensaje del día, o antes si pregunta precios o el catálogo.
# Solo cuando el negocio ya va cerca de lo gratis de Meta
# (whatsapp_near_free_limit): antes de eso no ahorra nada y es un paso extra.
INVITE_AFTER_MESSAGES = 3
_INVITE_TTL_SECONDS = 2 * 24 * 3600
_SHOPPING_WORDS = (
    "precio", "precios", "cuanto", "cuánto", "cuesta", "cuestan", "catalogo", "catálogo",
    "menu", "menú", "que tienen", "qué tienen", "que venden", "qué venden", "productos",
    "servicios", "promocion", "promoción", "promociones",
)


def portal_invite_line(contact_id: uuid.UUID) -> str:
    return f"\n\n💬 ¿Seguimos por aquí? Platica conmigo en la web, con fotos y precios: {portal_url(contact_id)}"


async def maybe_portal_invite(redis, contact_id: uuid.UUID | None, customer_text: str, reply: str) -> str:
    """La línea de invitación, o "" si hoy ya se le mandó, todavía no toca, o
    la respuesta ya trae su link (confirmaciones de cita/pedido)."""
    if redis is None or contact_id is None or not settings.SECRET_KEY or "/c/" in reply:
        return ""
    from datetime import datetime

    from app.services.availability_service import TZ

    today = datetime.now(TZ).strftime("%Y-%m-%d")
    try:
        count = await redis.incr(f"portal_invite_count:{contact_id}:{today}")
        if count == 1:
            await redis.expire(f"portal_invite_count:{contact_id}:{today}", _INVITE_TTL_SECONDS)
        text = (customer_text or "").lower()
        if count < INVITE_AFTER_MESSAGES and not any(w in text for w in _SHOPPING_WORDS):
            return ""
        first_today = await redis.set(f"portal_invited:{contact_id}:{today}", "1", nx=True, ex=_INVITE_TTL_SECONDS)
    except Exception:
        return ""
    return portal_invite_line(contact_id) if first_today else ""


_REPLIES_CACHE_SECONDS = 600


async def whatsapp_replies_this_month(db, redis, advertiser_id: uuid.UUID) -> int:
    """Respuestas por WhatsApp de este negocio en el mes (las que Meta cuenta
    como mensajes de servicio: salientes, sin campaña). Se guarda 10 minutos
    en Redis para no contar en cada mensaje."""
    from datetime import datetime, timezone

    from sqlalchemy import func, select

    from app.models.message import Message

    now = datetime.now(timezone.utc)
    key = f"wa_replies_month:{advertiser_id}:{now:%Y-%m}"
    if redis is not None:
        try:
            cached = await redis.get(key)
            if cached is not None:
                return int(cached)
        except Exception:
            logger.debug("[PORTAL] replies cache read failed", exc_info=True)
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    count = (await db.execute(
        select(func.count()).where(
            Message.advertiser_id == advertiser_id,
            Message.direction == "outbound",
            Message.channel.is_(None),
            Message.campaign_id.is_(None),
            Message.created_at >= first_of_month,
        )
    )).scalar_one()
    if redis is not None:
        try:
            await redis.set(key, str(count), ex=_REPLIES_CACHE_SECONDS)
        except Exception:
            logger.debug("[PORTAL] replies cache write failed", exc_info=True)
    return count


async def whatsapp_near_free_limit(db, redis, advertiser_id: uuid.UUID) -> bool:
    return await whatsapp_replies_this_month(db, redis, advertiser_id) >= settings.PORTAL_INVITE_FROM_WA_REPLIES

