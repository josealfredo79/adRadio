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


# Meta acepta el texto libre fuera de la ventana de 24h (200 con wamid) y lo
# rechaza segundos después por webhook (131047), así que no hay error con qué
# caer a la plantilla. Por eso se anota cuándo nos escribió cada número y se
# decide antes de mandar. 5 min de margen para no rozar el corte de Meta.
_WINDOW_KEY = "central_window:{}"
_WINDOW_SECONDS = 24 * 3600 - 300


async def mark_window_open(from_number: str, sent_at: str | int | None = None) -> None:
    """`from_number` le escribió al central (a la hora `sent_at` de Meta, en
    segundos): 24h de texto libre contadas desde ahí, no desde que llegó el
    webhook — Meta reenvía tarde los que no pudimos recibir."""
    from app.core.redis import get_redis_optional

    ttl = _WINDOW_SECONDS
    try:
        ttl -= max(0, int(time.time()) - int(sent_at)) if sent_at else 0
    except (TypeError, ValueError):
        pass
    if ttl <= 0:
        return
    redis = await get_redis_optional()
    if redis is None:
        return
    try:
        await redis.set(_WINDOW_KEY.format(normalize_recipient(from_number)), "1", ex=ttl)
    except Exception:
        logger.warning("[PLATFORM WA] Could not record the 24h window", exc_info=True)


async def _window_open(recipient: str) -> bool | None:
    """True/False según si nos escribió en 24h; None si Redis no responde."""
    from app.core.redis import get_redis_optional

    redis = await get_redis_optional()
    if redis is None:
        return None
    try:
        return bool(await redis.exists(_WINDOW_KEY.format(recipient)))
    except Exception:
        logger.warning("[PLATFORM WA] Could not read the 24h window", exc_info=True)
        return None


def _template_param(body: str) -> str:
    # Meta rechaza parámetros con saltos de línea, tabs o 4+ espacios seguidos.
    flat = " ".join(body.split())
    if len(flat) > _TEMPLATE_PARAM_MAX:
        flat = flat[: _TEMPLATE_PARAM_MAX - 1] + "…"
    return flat


async def send_platform_text(
    to: str, body: str, template: tuple[str, list[str]] | None = None
) -> tuple[str | None, str | None]:
    """Manda `body` al dueño desde el número central. Si nos escribió en las
    últimas 24h, como texto libre (se ve mejor: conserva saltos de línea); si
    no, o si Meta rechaza el texto, con la plantilla utility, que no depende
    de la ventana. Sin Redis no se sabe: se intenta el texto libre como antes.
    `template` = (nombre, variables) de una plantilla propia de ese aviso; sin
    ella va la genérica con todo `body` en {{1}}. Devuelve (wamid, error)."""
    if not platform_enabled():
        return None, "platform_not_configured"

    phone_number_id = settings.IARADIO_WA_PHONE_NUMBER_ID
    token = await platform_token()
    if not token:
        return None, "platform_not_configured"
    recipient = normalize_recipient(to)

    if await _window_open(recipient) is not False:
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
    else:
        logger.info("[PLATFORM WA] %s has not written in 24h — sending the template", to)

    name, params = template or (settings.IARADIO_OWNER_TEMPLATE_NAME, [body])

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
                    "name": name,
                    "language": {"code": settings.IARADIO_OWNER_TEMPLATE_LANG},
                    "components": [
                        {"type": "body", "parameters": [{"type": "text", "text": _template_param(p)} for p in params]}
                    ],
                },
            },
        )
        return (data.get("messages") or [{}])[0].get("id"), None
    except MetaApiError as e:
        logger.error("[PLATFORM WA] Template %s to %s failed too: %s", name, to, e)
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


async def send_platform_list(to: str, body: str, rows: list[tuple[str, str]],
                             button_text: str = "Ver opciones") -> tuple[str | None, str | None]:
    """Mensaje con una lista de hasta 10 opciones (título ≤ 24 caracteres).
    Se usa cuando hay más de 3 opciones (estilos, fotos, descuentos). Si Meta
    lo rechaza, manda el texto con las opciones numeradas — el dueño puede
    contestar el número o el texto."""
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
                    "type": "list",
                    "body": {"text": body[:1024]},
                    "action": {
                        "button": button_text[:20],
                        "sections": [{
                            "rows": [
                                {"id": rid[:200], "title": title[:24]}
                                for rid, title in rows[:10]
                            ],
                        }],
                    },
                },
            },
        )
        return (data.get("messages") or [{}])[0].get("id"), None
    except MetaApiError as e:
        logger.warning("[PLATFORM WA] List to %s failed (%s) — sending as text", to, e)
        options = "\n".join(f"{i}. {title}" for i, (_, title) in enumerate(rows[:10], 1))
        return await send_platform_text(to, f"{body}\n\n{options}")


async def send_platform_image(to: str, link: str, caption: str | None = None) -> tuple[str | None, str | None]:
    """Imagen al dueño por link público (la vista previa de una campaña con
    foto). Si Meta la rechaza, manda el link para que la abra."""
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
                "type": "image",
                "image": {"link": link, **({"caption": caption[:1024]} if caption else {})},
            },
        )
        return (data.get("messages") or [{}])[0].get("id"), None
    except MetaApiError as e:
        logger.warning("[PLATFORM WA] Image to %s failed (%s) — sending the link", to, e)
        return await send_platform_text(to, f"{caption}\n{link}" if caption else link)


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
