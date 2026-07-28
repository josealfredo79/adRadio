"""
WhatsApp Cloud API sender — replaces twilio_service.py.

Same public function names/return shape as the old Twilio service
((external_id, error) tuples) to minimize call-site churn, but every
function takes the advertiser's `User` row instead of a bare `from_number`
string, because sending via Meta needs a per-advertiser phone_number_id +
decrypted access token, not just a phone number.
"""
import logging

from app.config import settings
from app.core.crypto import EncryptedValue, decrypt_secret
from app.models.user import User
from app.services.meta_client import MetaApiError, graph_request, normalize_recipient

logger = logging.getLogger(__name__)


def _connection(advertiser: User) -> tuple[str, str] | None:
    """Return (phone_number_id, decrypted_token) for a connected advertiser, or None."""
    if advertiser.meta_connection_status != "connected" or not advertiser.meta_phone_number_id:
        return None
    if not (advertiser.meta_token_cipher and advertiser.meta_token_iv and advertiser.meta_token_tag):
        return None
    try:
        token = decrypt_secret(
            EncryptedValue(
                cipher=advertiser.meta_token_cipher,
                iv=advertiser.meta_token_iv,
                tag=advertiser.meta_token_tag,
            )
        )
    except Exception as e:
        # Broad catch is deliberate: a decrypt failure of any kind should
        # degrade to "not connected", never crash the send/pipeline.
        logger.error("[META] Failed to decrypt token for advertiser=%s: %s", advertiser.id, e)
        return None
    return advertiser.meta_phone_number_id, token


async def send_whatsapp(to: str, body: str, *, advertiser: User) -> tuple[str | None, str | None]:
    """Send a plain-text WhatsApp message via the advertiser's Meta connection."""
    conn = _connection(advertiser)
    if conn is None:
        if settings.DEBUG:
            logger.debug("[META DEV] To: %s | Body: %s", to, body)
            return "DEV_WAMID", None
        logger.warning("[META] advertiser=%s has no active WhatsApp connection", advertiser.id)
        return None, "meta_not_connected"

    phone_number_id, token = conn
    try:
        data = await graph_request(
            f"{phone_number_id}/messages",
            token=token,
            method="POST",
            body={
                "messaging_product": "whatsapp",
                "to": normalize_recipient(to),
                "type": "text",
                "text": {"body": body},
            },
        )
        wamid = (data.get("messages") or [{}])[0].get("id")
        return wamid, None
    except MetaApiError as e:
        logger.error("[META ERROR] advertiser=%s to=%s: %s", advertiser.id, to, e)
        return None, str(e)[:100]


async def send_whatsapp_media(
    to: str, media_url: str, body: str = "", *, advertiser: User
) -> tuple[str | None, str | None]:
    """
    Send a WhatsApp audio message (voice notes / cuñas — the only media type
    this app sends today). Meta's audio type has no caption field, so a
    non-empty `body` is sent as a best-effort follow-up text message.
    """
    conn = _connection(advertiser)
    if conn is None:
        if settings.DEBUG:
            logger.debug("[META DEV] To: %s | Media: %s | Body: %s", to, media_url, body)
            return "DEV_WAMID", None
        logger.warning("[META] advertiser=%s has no active WhatsApp connection", advertiser.id)
        return None, "meta_not_connected"

    phone_number_id, token = conn
    try:
        data = await graph_request(
            f"{phone_number_id}/messages",
            token=token,
            method="POST",
            body={
                "messaging_product": "whatsapp",
                "to": normalize_recipient(to),
                "type": "audio",
                "audio": {"link": media_url},
            },
        )
        wamid = (data.get("messages") or [{}])[0].get("id")
    except MetaApiError as e:
        logger.error("[META MEDIA ERROR] advertiser=%s to=%s: %s", advertiser.id, to, e)
        return None, str(e)[:100]

    if body:
        try:
            await graph_request(
                f"{phone_number_id}/messages",
                token=token,
                method="POST",
                body={
                    "messaging_product": "whatsapp",
                    "to": normalize_recipient(to),
                    "type": "text",
                    "text": {"body": body},
                },
            )
        except MetaApiError as e:
            logger.warning("[META MEDIA CAPTION] follow-up text failed for advertiser=%s: %s", advertiser.id, e)

    return wamid, None


async def send_whatsapp_template(
    to: str,
    template_name: str,
    language: str = "es_MX",
    components: list[dict] | None = None,
    *,
    advertiser: User,
) -> tuple[str | None, str | None]:
    """
    Send a pre-approved WhatsApp template message — the safe way to send
    outside the 24h customer-service window. Unlike Twilio's opaque Content
    SID, Meta addresses templates by (name, language) with structured
    `components` for variable substitution.
    """
    conn = _connection(advertiser)
    if conn is None:
        if settings.DEBUG:
            logger.debug("[META DEV] Template: %s | To: %s", template_name, to)
            return "DEV_WAMID", None
        logger.warning("[META] advertiser=%s has no active WhatsApp connection", advertiser.id)
        return None, "meta_not_connected"

    phone_number_id, token = conn
    template_payload: dict = {"name": template_name, "language": {"code": language}}
    if components:
        template_payload["components"] = components

    try:
        data = await graph_request(
            f"{phone_number_id}/messages",
            token=token,
            method="POST",
            body={
                "messaging_product": "whatsapp",
                "to": normalize_recipient(to),
                "type": "template",
                "template": template_payload,
            },
        )
        wamid = (data.get("messages") or [{}])[0].get("id")
        return wamid, None
    except MetaApiError as e:
        logger.error("[META TEMPLATE ERROR] advertiser=%s to=%s template=%s: %s", advertiser.id, to, template_name, e)
        return None, str(e)[:100]


async def send_whatsapp_buttons(
    to: str,
    body: str,
    template_name: str,
    components: list[dict] | None = None,
    *,
    advertiser: User,
) -> tuple[str | None, str | None]:
    """Send an interactive/button template. Falls back to plain text if no template is configured."""
    if template_name:
        return await send_whatsapp_template(
            to=to,
            template_name=template_name,
            components=components,
            advertiser=advertiser,
        )
    return await send_whatsapp(to=to, body=body, advertiser=advertiser)
