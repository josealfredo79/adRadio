"""
Radio service — genera cuñas publicitarias con voz de locutor latinoamericano.

Flujo:
  1. Claude genera el guión estilo radio AM/FM
  2. edge-tts sintetiza la voz (es-MX-JorgeNeural)
  3. pydub mezcla la voz con el jingle de fondo
  4. El audio .ogg se sube a Cloudflare R2
  5. Se envía como nota de voz por WhatsApp (Twilio)

Requisitos del sistema: ffmpeg instalado (para pydub)
"""
import asyncio
import io
import os
import tempfile
from pathlib import Path

import edge_tts

from app.services.claude_service import _get_client
from app.services.storage_service import upload_bytes
from app.config import settings

# Voces disponibles por país — todas masculinas, estilo locutor
LOCUTOR_VOICES = {
    "mx": "es-MX-JorgeNeural",     # México — tono cálido, radio AM
    "co": "es-CO-GonzaloNeural",   # Colombia
    "ar": "es-AR-TomasNeural",     # Argentina
    "es": "es-ES-AlvaroNeural",    # España (fallback)
    "default": "es-MX-JorgeNeural",
}

GUION_SYSTEM_PROMPT = """Eres un guionista experto en radio AM/FM latinoamericana de los años 80-90.
Escribe el guión de una cuña publicitaria de 20-25 segundos.

Reglas:
- Tono cálido, nostálgico, como locutor de radio de barrio
- Empieza con una frase gancho (pregunta o dato sorprendente)
- Menciona el negocio con naturalidad en medio del guión
- Termina con llamada a acción clara y WhatsApp o teléfono
- SOLO el texto del locutor — sin acotaciones de dirección ni indicaciones de sonido
- Máximo 200 palabras
- Lenguaje latinoamericano coloquial, no corporativo
"""

GUION_COMUNITARIO_PROMPT = """Eres un locutor de radio comunitaria latinoamericana — al estilo de las emisoras
que nacieron para educar, reflexionar y conectar vecinos, no para vender.

La radio fue inventada para llevar conocimiento a quien no tenía acceso.
Cada cuña de Radio Comunitaria honra ese origen: primero da valor genuino, luego —
con honestidad y sin presión — menciona quién patrocina ese momento.

Estructura obligatoria (30 segundos máximo):
1. REFLEXIÓN O DATO ÚTIL (12-15 seg): un consejo práctico, dato cultural o reflexión
   breve relacionada con la categoría del negocio. Genuinamente útil, no un truco para vender.
2. PAUSA NATURAL: "... Este momento fue traído a ti por..."
3. MENCIÓN DEL NEGOCIO (8-10 seg): presentación cálida y honesta, sin hipérboles.
   Qué hace, dónde están, cómo contactarlos.

Reglas:
- La reflexión debe tener valor por sí misma, aunque nadie compre nada
- Tono de maestro de barrio, no de vendedor
- Sin signos de exclamación múltiples
- Sin frases como "¡Oferta única!" o "¡No te lo pierdas!"
- Máximo 220 palabras
- SOLO el texto del locutor
"""


async def generate_radio_script(
    business_name: str,
    message_or_intent: str,
    country: str = "mx",
    mode: str = "classic",  # "classic" | "comunitaria"
) -> str:
    """Claude genera el guión de la cuña al estilo radio latinoamericana."""
    client = _get_client()

    system = GUION_COMUNITARIO_PROMPT if mode == "comunitaria" else GUION_SYSTEM_PROMPT

    if mode == "comunitaria":
        prompt = f"""Escribe una cuña de Radio Comunitaria para:

Negocio: {business_name}
Categoría / mensaje: {message_or_intent}
País: {country.upper()}

Recuerda: primero el valor genuino, luego la mención honesta del negocio."""
    else:
        prompt = f"""Escribe una cuña de radio para:

Negocio: {business_name}
Mensaje a comunicar: {message_or_intent}
País: {country.upper()}

Devuelve SOLO el texto que dirá el locutor."""

    response = await client.messages.create(
        model="claude-opus-4-5",
        max_tokens=500,
        temperature=0.8,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


async def text_to_speech(text: str, voice: str, rate: str = "-8%", pitch: str = "-3Hz") -> bytes:
    """Sintetiza voz con edge-tts. Retorna bytes del archivo MP3."""
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data


def mix_with_jingle(voice_bytes: bytes, jingle_path: str | None = None, volume_voice: float = 1.0, volume_jingle: float = 0.15) -> bytes:
    """
    Mezcla la voz del locutor con un jingle de fondo usando pydub.
    Si no hay jingle disponible, retorna solo la voz.
    """
    try:
        from pydub import AudioSegment  # type: ignore

        voice = AudioSegment.from_mp3(io.BytesIO(voice_bytes))

        if jingle_path and Path(jingle_path).exists():
            jingle = AudioSegment.from_file(jingle_path)
            # Loop jingle to match voice duration + 2s fade out
            if len(jingle) < len(voice) + 2000:
                loops = (len(voice) + 2000) // len(jingle) + 1
                jingle = jingle * loops
            jingle = jingle[: len(voice) + 2000]
            jingle = jingle.fade_out(2000)
            jingle = jingle - (20 - int(volume_jingle * 20))  # reduce volume

            mixed = voice.overlay(jingle)
        else:
            mixed = voice

        # Export as OGG for WhatsApp voice notes
        out = io.BytesIO()
        mixed.export(out, format="ogg", codec="libopus")
        return out.getvalue()

    except Exception:
        # If pydub/ffmpeg not available, return raw MP3
        return voice_bytes


async def generate_radio_ad(
    business_name: str,
    message_or_intent: str,
    country: str = "mx",
    jingle_path: str | None = None,
    _script: str | None = None,
    mode: str = "classic",  # "classic" | "comunitaria"
) -> str:
    """
    Pipeline completo: guión → voz → mezcla → R2 → URL pública.
    Si se provee _script, se omite la llamada a Claude.
    Retorna la URL del archivo de audio en R2.
    """
    # 1. Generar guión con Claude (o usar el provisto)
    script = _script or await generate_radio_script(business_name, message_or_intent, country, mode=mode)

    # 2. Sintetizar voz
    voice = LOCUTOR_VOICES.get(country, LOCUTOR_VOICES["default"])
    mp3_bytes = await text_to_speech(script, voice)

    # 3. Mezclar con jingle
    audio_bytes = mix_with_jingle(mp3_bytes, jingle_path)

    # 4. Subir a R2
    ext = "ogg" if audio_bytes[:4] == b"OggS" else "mp3"
    key = f"radio/{business_name.lower().replace(' ', '_')}_{os.urandom(4).hex()}.{ext}"
    content_type = "audio/ogg" if ext == "ogg" else "audio/mpeg"
    url = await upload_bytes(audio_bytes, key, content_type=content_type)

    if not url:
        raise RuntimeError("No se pudo subir el audio a R2. Verifica las variables CF_R2_*.")

    return url
