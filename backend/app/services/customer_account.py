"""Cuenta del cliente en IaRadio (/mi) — entra con su número y un código que
le llega por WhatsApp desde el número central, y ve en un solo lugar todos
los negocios IaRadio donde es cliente (cada uno es un Contact distinto con
el mismo teléfono).

Sin contraseñas ni tabla de usuarios: el token es el teléfono canónico + una
fecha de vencimiento firmados con SECRET_KEY (mismo modelo que el link del
portal, portal_service.py). El código vive solo en Redis, hasheado.
"""
import base64
import hashlib
import hmac
import logging
import re
import secrets
import time

from sqlalchemy import case, func

from app.config import settings
from app.models.contact import Contact

logger = logging.getLogger(__name__)

_DOMAIN = b"customer-account:v1:"
_SIG_BYTES = 16
TOKEN_TTL_SECONDS = 180 * 24 * 3600  # medio año: es la "app" del cliente

CODE_TTL_SECONDS = 10 * 60
CODE_MAX_ATTEMPTS = 5
CODE_RESEND_SECONDS = 60
CODE_DAILY_MAX = 5  # por número — cada código por WhatsApp lo cobra Meta


def canonical_phone(raw: str | None) -> str | None:
    """Solo dígitos, con lada de país. México: 10 dígitos → 52 + número, y el
    521 viejo de WhatsApp → 52. None si no parece un teléfono."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:
        digits = "52" + digits
    elif len(digits) == 13 and digits.startswith("521"):
        digits = "52" + digits[3:]
    if not 11 <= len(digits) <= 15:
        return None
    return digits


def contact_phone_canonical():
    """La misma normalización que canonical_phone(), en SQL, sobre
    Contact.phone (guardado con o sin +, con 521, a 10 dígitos si vino de CSV)."""
    digits = func.regexp_replace(Contact.phone, r"\D", "", "g")
    return case(
        (func.length(digits) == 10, func.concat("52", digits)),
        ((func.length(digits) == 13) & digits.startswith("521"), func.concat("52", func.substr(digits, 4))),
        else_=digits,
    )


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: bytes) -> bytes:
    return hmac.new(settings.SECRET_KEY.encode(), _DOMAIN + payload, hashlib.sha256).digest()[:_SIG_BYTES]


def make_account_token(phone: str, now: float | None = None) -> str:
    payload = f"{phone}|{int((now or time.time()) + TOKEN_TTL_SECONDS)}".encode()
    return f"{_b64(payload)}.{_b64(_sign(payload))}"


def read_account_token(token: str, now: float | None = None) -> str | None:
    """El teléfono canónico, o None (mal formado, firma que no cuadra o vencido)."""
    if not settings.SECRET_KEY or not token:
        return None
    try:
        payload_part, sig_part = token.split(".", 1)
        payload = _unb64(payload_part)
        sig = _unb64(sig_part)
        phone, expires = payload.decode().split("|", 1)
        expires_at = int(expires)
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    if expires_at < (now or time.time()):
        return None
    return phone


def _code_hash(phone: str, code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"otp:{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def _text(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


class CodeError(Exception):
    pass


async def issue_code(redis, phone: str) -> str:
    """Genera y guarda el código (hasheado). Lanza CodeError si pidió uno
    hace menos de un minuto o ya van muchos hoy."""
    if not await redis.set(f"otp_cooldown:{phone}", "1", nx=True, ex=CODE_RESEND_SECONDS):
        raise CodeError("Espera un minuto para pedir otro código.")
    day_key = f"otp_day:{phone}:{time.strftime('%Y-%m-%d')}"
    sent_today = await redis.incr(day_key)
    if sent_today == 1:
        await redis.expire(day_key, 24 * 3600)
    if sent_today > CODE_DAILY_MAX:
        raise CodeError("Ya pediste muchos códigos hoy. Intenta mañana.")
    code = f"{secrets.randbelow(10**6):06d}"
    await redis.set(f"otp:{phone}", _code_hash(phone, code), ex=CODE_TTL_SECONDS)
    await redis.set(f"otp_tries:{phone}", "0", ex=CODE_TTL_SECONDS)
    return code


async def check_code(redis, phone: str, code: str) -> bool:
    """True una sola vez por código; tras CODE_MAX_ATTEMPTS fallos el código muere."""
    stored = await redis.get(f"otp:{phone}")
    if stored is None:
        return False
    tries = await redis.incr(f"otp_tries:{phone}")
    if tries > CODE_MAX_ATTEMPTS:
        await redis.delete(f"otp:{phone}")
        return False
    if not hmac.compare_digest(_text(stored), _code_hash(phone, (code or "").strip())):
        return False
    await redis.delete(f"otp:{phone}")
    return True


async def send_code(phone: str, code: str) -> bool:
    """Por la plantilla de autenticación del número central (con botón
    "Copiar código"). Sin plantilla configurada no hay cómo — False."""
    from app.services.meta_client import MetaApiError, graph_request
    from app.services.platform_whatsapp import platform_enabled, platform_token

    if not (platform_enabled() and settings.IARADIO_OTP_TEMPLATE_NAME):
        logger.warning("[ACCOUNT] Central number or OTP template not configured")
        return False
    token = await platform_token()
    if not token:
        return False
    try:
        await graph_request(
            f"{settings.IARADIO_WA_PHONE_NUMBER_ID}/messages",
            token=token,
            method="POST",
            body={
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "template",
                "template": {
                    "name": settings.IARADIO_OTP_TEMPLATE_NAME,
                    "language": {"code": settings.IARADIO_OTP_TEMPLATE_LANG},
                    "components": [
                        {"type": "body", "parameters": [{"type": "text", "text": code}]},
                        {"type": "button", "sub_type": "url", "index": "0",
                         "parameters": [{"type": "text", "text": code}]},
                    ],
                },
            },
        )
        return True
    except MetaApiError as e:
        logger.error("[ACCOUNT] OTP template send failed: %s", e)
        return False
