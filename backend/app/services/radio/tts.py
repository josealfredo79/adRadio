"""
Text-to-Speech for radio ads.
Supports edge-tts, Fish Audio, and Google Cloud TTS.
"""

import logging

logger = logging.getLogger(__name__)


LOCUTOR_VOICES = {
    "mx": "es-MX-JorgeNeural",
    "co": "es-CO-GonzaloNeural",
    "ar": "es-AR-TomasNeural",
    "es": "es-ES-AlvaroNeural",
    "default": "es-MX-JorgeNeural",
}

# Maps this app's edge-tts voice ids (see AVAILABLE_VOICES in app/api/v1/radio.py)
# to a gender/accent-correct Google Cloud voice. Google Cloud TTS has no
# separate es-MX/es-AR/es-CO catalog, only es-ES (Spain) and es-US (generic
# Latin American Spanish) — so all three Latin American accents collapse to
# the same es-US voice per gender; only the es-ES entries keep a distinct
# accent. Verified gender against the live Google API (voice names like
# "Neural2-F" are catalog letters, NOT a gender code).
GOOGLE_VOICE_MAP = {
    "es-MX-JorgeNeural": "es-US-Neural2-B",   # male
    "es-MX-DaliaNeural": "es-US-Neural2-A",   # female
    "es-AR-TomasNeural": "es-US-Neural2-B",   # male
    "es-AR-ElenaNeural": "es-US-Neural2-A",   # female
    "es-CO-GonzaloNeural": "es-US-Neural2-B", # male
    "es-CO-SalomeNeural": "es-US-Neural2-A",  # female
    "es-ES-AlvaroNeural": "es-ES-Neural2-F",  # male
    "es-ES-ElviraNeural": "es-ES-Neural2-A",  # female
}


async def _tts_fish_audio(text: str, voice_id: str | None) -> bytes:
    """Sintetiza voz con Fish Audio S2 (alta calidad). Retorna bytes MP3."""
    from fishaudio import AsyncFishAudio  # type: ignore

    from app.config import settings

    client = AsyncFishAudio(api_key=settings.FISH_AUDIO_API_KEY)
    buf = bytearray()
    stream = await client.tts.stream(
        text=text,
        reference_id=voice_id or None,
        format="mp3",
        latency="balanced",
    )
    async for chunk in stream:
        buf.extend(chunk)
    return bytes(buf)


async def _tts_edge(text: str, voice: str, rate: str = "-5%", pitch: str = "-5Hz") -> bytes:
    """Sintetiza voz con edge-tts (fallback gratuito). Retorna bytes MP3."""
    import edge_tts

    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data


# Voz de las respuestas en vivo (mascota, chat del cliente, Copiloto): edge-tts
# es gratis, pero Microsoft lo bloquea a ratos (403 desde oct-2026, edge-tts
# issue #490). Si falla, Google (ya configurado para la radio) y se salta
# edge un rato para no gastar tiempo en cada frase.
LIVE_EDGE_VOICE = "es-MX-DaliaNeural"
LIVE_GOOGLE_VOICE = "es-US-Neural2-A"  # femenina latina, la más parecida a Dalia
EDGE_COOLDOWN_SECONDS = 600
_edge_down_until = 0.0


async def speak_voice(text: str) -> bytes:
    """Una frase dicha en voz alta (MP3). Lanza si ninguna voz está disponible."""
    import time

    from app.config import settings

    global _edge_down_until
    if time.monotonic() >= _edge_down_until:
        try:
            audio = await _tts_edge(text, LIVE_EDGE_VOICE, rate="+0%", pitch="+0Hz")
            if audio:
                return audio
        except Exception as e:
            logger.warning("[TTS] edge-tts falló (%s); uso Google %d min", type(e).__name__, EDGE_COOLDOWN_SECONDS // 60)
        _edge_down_until = time.monotonic() + EDGE_COOLDOWN_SECONDS
    if not settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("Sin voz: edge-tts no responde y Google TTS no está configurado")
    return await _tts_google_cloud(text, LIVE_GOOGLE_VOICE)


async def _tts_google_cloud(text: str, voice_name: str = "es-ES-Neural2-F") -> bytes:
    """Sintetiza voz con Google Cloud Text-to-Speech (WaveNet). Retorna bytes MP3."""
    import json

    from google.cloud import texttospeech_v1 as tts

    from app.config import settings

    credentials_info = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON) if settings.GOOGLE_SERVICE_ACCOUNT_JSON else {}
    if not credentials_info:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON no está configurado.")

    client = tts.TextToSpeechAsyncClient.from_service_account_info(credentials_info)

    # language_code must match voice_name's locale (e.g. "es-US-Neural2-A" needs
    # "es-US", not "es-ES") or Google Cloud TTS rejects the request.
    language_code = "-".join(voice_name.split("-")[:2])

    synthesis_input = tts.SynthesisInput(text=text)
    voice = tts.VoiceSelectionParams(
        language_code=language_code,
        name=voice_name,
    )
    audio_config = tts.AudioConfig(
        audio_encoding=tts.AudioEncoding.MP3,
        speaking_rate=0.95,
        pitch=-0.5,
    )

    request = tts.SynthesizeSpeechRequest(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )

    response = await client.synthesize_speech(request=request)
    return response.audio_content


async def text_to_speech(text: str, voice: str, rate: str = "-5%", pitch: str = "-5Hz") -> bytes:
    """
    Sintetiza voz para la cuña de radio.
    - Si GOOGLE_TTS_PROVIDER="google" → usa Google Cloud TTS (WaveNet), mapeando
      la voz elegida (acento/género) a su equivalente de Google vía GOOGLE_VOICE_MAP.
    - Si FISH_AUDIO_API_KEY está configurado → usa Fish Audio S2 (calidad profesional).
    - Si no → usa edge-tts (gratuito, Microsoft Neural).
    """
    from app.config import settings

    if settings.GOOGLE_TTS_PROVIDER == "google":
        google_voice = GOOGLE_VOICE_MAP.get(voice) or settings.GOOGLE_TTS_VOICE_NAME or "es-ES-Neural2-F"
        return await _tts_google_cloud(text, google_voice)
    if settings.FISH_AUDIO_API_KEY:
        voice_id = settings.FISH_AUDIO_VOICE_ID or None
        return await _tts_fish_audio(text, voice_id)
    return await _tts_edge(text, voice, rate, pitch)
