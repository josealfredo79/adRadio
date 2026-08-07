"""
Whisper transcription service — uses Whisper via Groq's free tier (2,000
req/day, no card required) to transcribe incoming WhatsApp audio messages.
"""
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


async def transcribe_audio_bytes(audio_bytes: bytes, content_type: str = "audio/ogg") -> str | None:
    """
    Transcribe already-downloaded audio bytes with Whisper (via Groq).
    Returns the transcribed text, or None on failure. The Meta webhook
    handles its own media download/auth and calls this with the raw bytes.
    """
    if not settings.GROQ_API_KEY:
        logger.warning("[WHISPER] GROQ_API_KEY not set — skipping transcription")
        return None

    try:
        ext_map = {
            "audio/ogg": "ogg",
            "audio/mpeg": "mp3",
            "audio/mp4": "mp4",
            "audio/wav": "wav",
            "audio/webm": "webm",
            "audio/amr": "amr",
        }
        ext = "ogg"
        for mime, e in ext_map.items():
            if mime in content_type:
                ext = e
                break

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                files={
                    "file": (f"audio.{ext}", audio_bytes, content_type),
                    "model": (None, "whisper-large-v3-turbo"),
                    "language": (None, "es"),
                    "response_format": (None, "json"),
                },
            )
            response.raise_for_status()
            text = response.json().get("text", "").strip()
            logger.info("[WHISPER] Transcribed audio: %s chars", len(text))
            return text if text else None

    except Exception as e:
        logger.error("[WHISPER] Transcription failed: %s", e)
        return None
