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


async def _tts_google_cloud(text: str, voice_name: str = "es-ES-Neural2-F") -> bytes:
    """Sintetiza voz con Google Cloud Text-to-Speech (WaveNet). Retorna bytes MP3."""
    from google.cloud import texttospeech_v1 as tts
    import json
    from app.config import settings

    credentials_info = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON) if settings.GOOGLE_SERVICE_ACCOUNT_JSON else {}
    if not credentials_info:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON no está configurado.")

    client = tts.TextToSpeechAsyncClient.from_service_account_info(credentials_info)

    synthesis_input = tts.SynthesisInput(text=text)
    voice = tts.VoiceSelectionParams(
        language_code="es-ES",
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
    - Si GOOGLE_TTS_PROVIDER="google" → usa Google Cloud TTS (WaveNet).
    - Si FISH_AUDIO_API_KEY está configurado → usa Fish Audio S2 (calidad profesional).
    - Si no → usa edge-tts (gratuito, Microsoft Neural).
    """
    from app.config import settings

    if settings.GOOGLE_TTS_PROVIDER == "google":
        return await _tts_google_cloud(text, settings.GOOGLE_TTS_VOICE_NAME or "es-ES-Neural2-F")
    if settings.FISH_AUDIO_API_KEY:
        voice_id = settings.FISH_AUDIO_VOICE_ID or None
        return await _tts_fish_audio(text, voice_id)
    return await _tts_edge(text, voice, rate, pitch)
