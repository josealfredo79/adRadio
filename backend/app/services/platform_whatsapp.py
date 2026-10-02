"""
Número central de IaRadio — el canal con los DUEÑOS de los negocios.

A diferencia de meta_service.py (que manda desde el número de cada negocio a
sus clientes), aquí todo sale del WABA propio de IaRadio, configurado por
env (IARADIO_WA_*). Así los avisos al dueño no dependen de que el dueño le
haya escrito a SU propio número en las últimas 24h — con coexistencia el
dueño ni siquiera podría: su celular ES el número del negocio.

El token: IARADIO_WA_TOKEN si está; si no, el que ya tiene guardado (cifrado)
la cuenta cuyo bot es ese mismo número — el chip de IaRadio es también el bot
de la cuenta IaRadio, así no hay que copiar el secreto a otro lado.
"""
import logging
import time

from sqlalchemy import select

from app.config import settings
from app.core.crypto import EncryptedValue, decrypt_secret
from app.services.meta_client import MetaApiError, graph_request, normalize_recipient

logger = logging.getLogger(__name__)

# Límite de Meta para un parámetro de texto en el cuerpo de una plantilla.
_TEMPLATE_PARAM_MAX = 1024


_TOKEN_TTL_SECONDS = 600
_token_cache: tuple[str | None, float] = (None, 0.0)


def platform_enabled() -> bool:
    return bool(settings.IARADIO_WA_PHONE_NUMBER_ID)


async def platform_token() -> str | None:
    """Token del número central (ver docstring del módulo). Se guarda unos
    minutos en memoria; si se renueva el token de la cuenta, se toma solo."""
    global _token_cache
    if settings.IARADIO_WA_TOKEN:
        return settings.IARADIO_WA_TOKEN
    token, expires = _token_cache
    if token and time.monotonic() < expires:
        return token
    from app.database import AsyncSessionLocal
    from app.models.user import User

    try:
        async with AsyncSessionLocal() as db:
            owner = (await db.execute(
                select(User).where(User.meta_phone_number_id == settings.IARADIO_WA_PHONE_NUMBER_ID).limit(1)
            )).scalar_one_or_none()
        if owner is None or not owner.meta_token_cipher:
            logger.error("[PLATFORM WA] No token: set IARADIO_WA_TOKEN or connect the number as an account's bot")
            return None
        token = decrypt_secret(EncryptedValue(
            cipher=owner.meta_token_cipher, iv=owner.meta_token_iv, tag=owner.meta_token_tag,
        ))
    except Exception:
        logger.exception("[PLATFORM WA] Could not load the central number token")
        return None
    _token_cache = (token, time.monotonic() + _TOKEN_TTL_SECONDS)
    return token


def _template_param(body: str) -> str:
    # Meta rechaza parámetros con saltos de línea, tabs o 4+ espacios seguidos.
    flat = " ".join(body.split())
    if len(flat) > _TEMPLATE_PARAM_MAX:
        flat = flat[: _TEMPLATE_PARAM_MAX - 1] + "…"
    return flat


async def send_platform_text(to: str, body: str) -> tuple[str | None, str | None]:
    """Manda `body` al dueño desde el número central. Primero como texto libre
    (se ve mejor: conserva saltos de línea); si Meta lo rechaza — lo normal
    cuando el dueño no nos ha escrito en 24h — reintenta con la plantilla
    utility, que no depende de la ventana. Devuelve (wamid, error)."""
    if not platform_enabled():
        return None, "platform_not_configured"

    phone_number_id = settings.IARADIO_WA_PHONE_NUMBER_ID
    token = await platform_token()
    if not token:
        return None, "platform_not_configured"
    recipient = normalize_recipient(to)

    try:
        data = await graph_request(
            f"{phone_number_id}/messages",
            token=token,
            method="POST",
            body={
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "text",
                "text": {"body": body},
            },
        )
        return (data.get("messages") or [{}])[0].get("id"), None
    except MetaApiError as e:
        logger.info("[PLATFORM WA] Free-form to %s rejected (%s) — falling back to template", to, e)

    try:
        data = await graph_request(
            f"{phone_number_id}/messages",
            token=token,
            method="POST",
            body={
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "template",
                "template": {
                    "name": settings.IARADIO_OWNER_TEMPLATE_NAME,
                    "language": {"code": settings.IARADIO_OWNER_TEMPLATE_LANG},
                    "components": [
                        {"type": "body", "parameters": [{"type": "text", "text": _template_param(body)}]}
                    ],
                },
            },
        )
        return (data.get("messages") or [{}])[0].get("id"), None
    except MetaApiError as e:
        logger.error("[PLATFORM WA] Template to %s failed too: %s", to, e)
        return None, str(e)[:100]


async def send_platform_buttons(to: str, body: str, buttons: list[tuple[str, str]]) -> tuple[str | None, str | None]:
    """Mensaje con botones de respuesta rápida (máx. 3; título ≤ 20 caracteres).
    Solo se usa respondiendo a algo que el dueño acaba de escribir, así que
    siempre cae dentro de la ventana de 24h. Si Meta lo rechaza, manda el
    texto con las opciones escritas — el dueño puede contestar tecleándolas."""
    token = await platform_token() if platform_enabled() else None
    if not token:
        return None, "platform_not_configured"
    try:
        data = await graph_request(
            f"{settings.IARADIO_WA_PHONE_NUMBER_ID}/messages",
            token=token,
            method="POST",
            body={
                "messaging_product": "whatsapp",
                "to": normalize_recipient(to),
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body[:1024]},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": bid, "title": title[:20]}}
                            for bid, title in buttons[:3]
                        ]
                    },
                },
            },
        )
        return (data.get("messages") or [{}])[0].get("id"), None
    except MetaApiError as e:
        logger.warning("[PLATFORM WA] Buttons to %s failed (%s) — sending as text", to, e)
        options = " / ".join(title for _, title in buttons)
        return await send_platform_text(to, f"{body}\n\nResponde: {options}")


async def send_platform_audio(to: str, link: str) -> tuple[str | None, str | None]:
    """Nota de voz al dueño (OGG/Opus por link público). Solo se usa
    contestando una nota de voz que el dueño acaba de mandar — siempre dentro
    de la ventana de 24h, así que no hay plantilla de respaldo: si falla,
    quien llama manda el texto."""
    token = await platform_token() if platform_enabled() else None
    if not token:
        return None, "platform_not_configured"
    try:
        data = await graph_request(
            f"{settings.IARADIO_WA_PHONE_NUMBER_ID}/messages",
            token=token,
            method="POST",
            body={
                "messaging_product": "whatsapp",
                "to": normalize_recipient(to),
                "type": "audio",
                "audio": {"link": link},
            },
        )
        return (data.get("messages") or [{}])[0].get("id"), None
    except MetaApiError as e:
        logger.warning("[PLATFORM WA] Audio to %s failed: %s", to, e)
        return None, str(e)[:100]
