"""
Radio ad generation package.
Split from radio_service.py for maintainability.
"""

import logging
import os

from app.services.radio.scripts import generate_radio_script
from app.services.radio.tts import text_to_speech, LOCUTOR_VOICES
from app.services.radio.audio import get_jingle_path, mix_with_jingle

logger = logging.getLogger(__name__)


async def generate_radio_ad(
    business_name: str,
    message_or_intent: str,
    country: str = "mx",
    jingle_path: str | None = None,
    _script: str | None = None,
    mode: str = "classic",
    business_category: str | None = None,
    voice_id: str | None = None,
    day_variant: int = 0,
) -> str:
    """
    Pipeline completo: guión → voz → mezcla → R2 → URL pública.
    Si se provee _script, se omite la llamada a Claude.
    Retorna la URL del archivo de audio en R2.
    """
    from app.services.storage_service import upload_bytes

    script = _script or await generate_radio_script(
        business_name, message_or_intent, country, mode=mode,
        business_category=business_category,
    )

    voice = voice_id or LOCUTOR_VOICES.get(country, LOCUTOR_VOICES["default"])
    try:
        mp3_bytes = await text_to_speech(script, voice)
        logger.info("[RADIO] TTS generated %d bytes with voice %s", len(mp3_bytes), voice)
    except Exception as tts_err:
        logger.error("[RADIO] TTS failed: %s", tts_err)
        raise RuntimeError(f"TTS failed: {tts_err}") from tts_err

    resolved_jingle = jingle_path or get_jingle_path(business_category)
    logger.info("[RADIO] Using jingle: %s", resolved_jingle)

    try:
        jingle_offset_ratio = (day_variant % 7) / 7.0
        audio_bytes = mix_with_jingle(mp3_bytes, resolved_jingle, jingle_offset_ratio=jingle_offset_ratio)
        logger.info("[RADIO] Mixed audio: %d bytes (variant day=%d, offset=%.2f)", len(audio_bytes), day_variant, jingle_offset_ratio)
    except Exception as mix_err:
        logger.error("[RADIO] Mix failed: %s", mix_err)
        raise RuntimeError(f"Mix failed: {mix_err}") from mix_err

    import re
    ext = "ogg" if audio_bytes[:4] == b"OggS" else "mp3"
    safe_slug = re.sub(r'[^a-z0-9_]', '', business_name.lower().replace(' ', '_'))
    key = f"radio/{safe_slug}_{os.urandom(4).hex()}.{ext}"
    content_type = "audio/ogg" if ext == "ogg" else "audio/mpeg"
    url = await upload_bytes(audio_bytes, key, content_type=content_type)

    if not url:
        raise RuntimeError("No se pudo guardar el audio. Verifica el almacenamiento.")

    return url
