"""
Twilio WhatsApp service.
"""
import logging
import random
import asyncio

from twilio.rest import Client  # type: ignore

from app.config import settings

logger = logging.getLogger(__name__)

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _client


async def send_whatsapp(to: str, body: str, from_number: str | None = None) -> tuple[str | None, str | None]:
    """
    Send a WhatsApp message via Twilio.
    Returns (sid, error_message) tuple.
    'to' should be in E.164 format (e.g. +521234567890).
    'from_number' is the advertiser's own WhatsApp number; falls back to
    the global TWILIO_WHATSAPP_NUMBER (shared IaRadio sender).
    """
    sender = from_number or settings.TWILIO_WHATSAPP_NUMBER
    if not settings.TWILIO_ACCOUNT_SID:
        logger.debug("[TWILIO DEV] From: %s | To: %s | Body: %s", sender, to, body)
        return "DEV_SID", None

    client = _get_client()
    try:
        message = await asyncio.to_thread(
            client.messages.create,
            from_=f"whatsapp:{sender}",
            to=f"whatsapp:{to}",
            body=body,
        )
        return message.sid, None
    except Exception as e:
        error_msg = str(e)
        logger.error("[TWILIO ERROR] %s", error_msg)
        return None, error_msg[:100]


async def send_whatsapp_media(to: str, media_url: str, body: str = "", from_number: str | None = None) -> tuple[str | None, str | None]:
    """
    Send a WhatsApp media message (voice note, image, etc.) via Twilio.
    Returns (sid, error_message) tuple.
    'media_url' must be a publicly accessible URL.
    'from_number' is the advertiser's own WhatsApp number; falls back to
    the global TWILIO_WHATSAPP_NUMBER (shared IaRadio sender).
    """
    sender = from_number or settings.TWILIO_WHATSAPP_NUMBER
    if not settings.TWILIO_ACCOUNT_SID:
        logger.debug("[TWILIO DEV] From: %s | To: %s | Media: %s | Body: %s", sender, to, media_url, body)
        return "DEV_SID", None

    client = _get_client()
    try:
        kwargs: dict = {
            "from_": f"whatsapp:{sender}",
            "to": f"whatsapp:{to}",
            "media_url": [media_url],
        }
        if body:
            kwargs["body"] = body
        message = await asyncio.to_thread(
            client.messages.create,
            **kwargs
        )
        return message.sid, None
    except Exception as e:
        error_msg = str(e)
        logger.error("[TWILIO MEDIA ERROR] %s", error_msg)
        return None, error_msg[:100]


def anti_ban_delay() -> int:
    """Return random delay in seconds (25-90) for anti-ban compliance."""
    return random.randint(25, 90)


def is_human_hour(timezone_offset: int = -6) -> bool:
    """Check if current time is within 8am-9pm in given UTC offset."""
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=timezone_offset))
    now = datetime.now(tz)
    return 8 <= now.hour < 21
