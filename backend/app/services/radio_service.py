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
import math
import os
import tempfile
import unicodedata
from pathlib import Path

import edge_tts

from app.services.claude_service import _get_client
from app.services.storage_service import upload_bytes
from app.config import settings

# Directorio donde viven los jingles de fondo
JINGLES_DIR = Path(__file__).parent.parent / "static" / "jingles"

def _norm(s: str) -> str:
    """Normaliza a ASCII lowercase para comparación de categorías (elimina tildes)."""
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower().strip()


# Mapa de categoría de negocio → archivo de jingle
CATEGORY_JINGLE_MAP: dict[str, str] = {
    # Inmobiliaria / terrenos
    "inmobiliaria": "inmobiliaria.mp3",
    "bienes raices": "inmobiliaria.mp3",
    "terrenos": "inmobiliaria.mp3",
    "construccion": "inmobiliaria.mp3",
    # Restaurante / comida
    "restaurante": "restaurante.mp3",
    "comida": "restaurante.mp3",
    "food": "restaurante.mp3",
    "cafeteria": "restaurante.mp3",
    "taqueria": "restaurante.mp3",
    # Tienda / retail
    "tienda": "tienda.mp3",
    "retail": "tienda.mp3",
    "ropa": "tienda.mp3",
    "moda": "tienda.mp3",
    "boutique": "tienda.mp3",
    # Tecnología
    "tecnologia": "tecnologia.mp3",
    "tech": "tecnologia.mp3",
    "software": "tecnologia.mp3",
    "electronica": "tecnologia.mp3",
    # Salud / bienestar
    "salud": "salud.mp3",
    "medico": "salud.mp3",
    "farmacia": "salud.mp3",
    "bienestar": "salud.mp3",
    "spa": "salud.mp3",
    # Belleza / estética
    "belleza": "belleza.mp3",
    "estetica": "belleza.mp3",
    "salon": "belleza.mp3",
    "peluqueria": "belleza.mp3",
    "cosmeticos": "belleza.mp3",
    # Deportes / gimnasio
    "deportes": "deportes.mp3",
    "gimnasio": "deportes.mp3",
    "gym": "deportes.mp3",
    "fitness": "deportes.mp3",
    "deporte": "deportes.mp3",
    # Educación
    "educacion": "educacion.mp3",
    "escuela": "educacion.mp3",
    "academia": "educacion.mp3",
    "colegio": "educacion.mp3",
    "universidad": "educacion.mp3",
    "cursos": "educacion.mp3",
    # Automotriz
    "automotriz": "automotriz.mp3",
    "autos": "automotriz.mp3",
    "carros": "automotriz.mp3",
    "taller": "automotriz.mp3",
    "mecanica": "automotriz.mp3",
    "agencia": "automotriz.mp3",
    # Ferretería / hardware
    "ferreteria": "tienda.mp3",
    "ferreteria": "tienda.mp3",
    "herramientas": "tienda.mp3",
    # Panadería / cafetería
    "panaderia": "restaurante.mp3",
    "panaderia": "restaurante.mp3",
    "pasteleria": "restaurante.mp3",
    # Corporativo / servicios (default para todo lo demás)
    "corporativo": "corporativo.mp3",
    "servicios": "corporativo.mp3",
    "empresa": "corporativo.mp3",
    "consultoria": "corporativo.mp3",
}

JINGLE_DEFAULT = "generico.mp3"


def get_jingle_path(business_category: str | None) -> str | None:
    """Retorna la ruta al jingle según la categoría del negocio."""
    if not business_category:
        filename = JINGLE_DEFAULT
    else:
        cat = _norm(business_category)
        # Búsqueda exacta primero, luego por substring
        filename = CATEGORY_JINGLE_MAP.get(cat)
        if not filename:
            for key, val in CATEGORY_JINGLE_MAP.items():
                if key in cat or cat in key:
                    filename = val
                    break
            else:
                filename = JINGLE_DEFAULT

    path = JINGLES_DIR / filename
    return str(path) if path.exists() else None


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


async def _tts_fish_audio(text: str, voice_id: str | None) -> bytes:
    """Sintetiza voz con Fish Audio S2 (alta calidad). Retorna bytes MP3."""
    from fishaudio import AsyncFishAudio  # type: ignore

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
    """Sintetiza voz con edge-tts (fallback gratuito). Retorna bytes MP3.
    rate=-5%: ritmo ligeramente más lento, más solemne — estilo locutor.
    pitch=-5Hz: voz levemente más grave, más autoridad de radio.
    """
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data


async def text_to_speech(text: str, voice: str, rate: str = "-5%", pitch: str = "-5Hz") -> bytes:
    """
    Sintetiza voz para la cuña de radio.
    - Si FISH_AUDIO_API_KEY está configurado → usa Fish Audio S2 (calidad profesional).
    - Si no → usa edge-tts (gratuito, Microsoft Neural).
    """
    if settings.FISH_AUDIO_API_KEY:
        voice_id = settings.FISH_AUDIO_VOICE_ID or None
        return await _tts_fish_audio(text, voice_id)
    return await _tts_edge(text, voice, rate, pitch)


def _normalize_loudness(segment, target_dbfs: float = -16.0):
    """Normaliza el volumen a target_dbfs (estándar broadcast -16 LUFS aprox)."""
    diff = target_dbfs - segment.dBFS
    return segment.apply_gain(diff)


def _process_voice(voice: "AudioSegment") -> "AudioSegment":  # type: ignore[name-defined]
    """
    Procesamiento de voz estilo locutor de radio:
    - Elimina frecuencias muy bajas (<100 Hz) que enturbian la voz
    - Aplica presencia: pequeño boost que da claridad y brillo al locutor
    - Compresión suave (gain staging manual)
    """
    try:
        from pydub import AudioSegment  # type: ignore
        from pydub.effects import high_pass_filter, low_pass_filter, normalize  # type: ignore

        # High-pass filter: elimina graves innecesarios (rumble, breath bass)
        voice = high_pass_filter(voice, cutoff=120)

        # Normalize antes del boost para no saturar
        voice = normalize(voice)

        # Boost de presencia +2.5 dB — da claridad "radio" sin saturar
        voice = voice + 2.5

        return voice
    except Exception:
        return voice


def mix_with_jingle(
    voice_bytes: bytes,
    jingle_path: str | None = None,
    # Timing (ms)
    jingle_intro_ms: int = 2500,    # jingle suena solo al inicio
    jingle_outro_ms: int = 2000,    # jingle suena solo al final
    jingle_fade_out_ms: int = 1800, # fade out del outro
    # Niveles
    jingle_full_db: float = -12.0,  # nivel del jingle en intro/outro
    jingle_duck_db: float = -22.0,  # nivel del jingle mientras habla el locutor ("ducking")
    voice_target_dbfs: float = -10.0,  # nivel final de la voz
) -> bytes:
    """
    Mezcla profesional de radio con ducking automático:

    Estructura temporal:
      [0ms → intro_ms]              Jingle solo a volumen completo (intro)
      [intro_ms → intro+voz]        Jingle BAJA (duck) mientras habla el locutor
      [fin_voz → fin_voz+outro_ms]  Jingle SUBE a volumen completo (outro)
      [outro → fade_out]            Fade out final

    Normalización final a -14 LUFS (estándar WhatsApp/mobile).
    """
    try:
        from pydub import AudioSegment  # type: ignore

        # ── Procesar voz ─────────────────────────────────────────────────
        voice = AudioSegment.from_mp3(io.BytesIO(voice_bytes))
        voice = _process_voice(voice)
        # Llevar la voz al nivel deseado
        diff = voice_target_dbfs - voice.dBFS
        voice = voice.apply_gain(diff)

        if not jingle_path or not Path(jingle_path).exists():
            # Sin jingle: exportar solo voz normalizada
            out = io.BytesIO()
            voice = _normalize_loudness(voice, -14.0)
            voice.export(out, format="ogg", codec="libopus", bitrate="128k")
            return out.getvalue()

        # ── Preparar jingle ──────────────────────────────────────────────
        jingle_raw = AudioSegment.from_file(jingle_path)

        total_needed_ms = jingle_intro_ms + len(voice) + jingle_outro_ms + jingle_fade_out_ms
        # Loop si es más corto que lo necesario
        if len(jingle_raw) < total_needed_ms:
            loops = total_needed_ms // len(jingle_raw) + 2
            jingle_raw = jingle_raw * loops
        jingle_raw = jingle_raw[:total_needed_ms]

        # Normalizar jingle a referencia para controlar bien los dB
        jingle_raw = _normalize_loudness(jingle_raw, -14.0)

        # ── Construir pista de jingle con ducking ────────────────────────
        #
        # Secciones:
        #   INTRO  → jingle a volumen completo (jingle_full_db relativo a ref)
        #   CUERPO → jingle duckeado mientras habla el locutor
        #   OUTRO  → jingle sube de nuevo + fade out

        intro  = jingle_raw[:jingle_intro_ms]
        body   = jingle_raw[jingle_intro_ms : jingle_intro_ms + len(voice)]
        outro  = jingle_raw[jingle_intro_ms + len(voice) : jingle_intro_ms + len(voice) + jingle_outro_ms + jingle_fade_out_ms]

        # Ajustar niveles por sección
        # intro: nivel completo
        intro_gain  = jingle_full_db - intro.dBFS
        intro       = intro.apply_gain(intro_gain)

        # body: ducking — baja significativamente para no tapar la voz
        body_gain   = jingle_duck_db - body.dBFS
        body        = body.apply_gain(body_gain)

        # Transición suave intro→body: fade in del duck (300ms)
        # Hacemos crossfade manual: la última parte del intro baja gradualmente
        XFADE = 300  # ms
        if len(intro) > XFADE:
            intro_xfade = intro[-XFADE:].fade(to_gain=body_gain - jingle_full_db, start=0, duration=XFADE)
            intro = intro[:-XFADE] + intro_xfade

        # outro: nivel completo con fade out
        outro_gain  = jingle_full_db - outro.dBFS
        outro       = outro.apply_gain(outro_gain)
        outro       = outro.fade_out(jingle_fade_out_ms)

        # Transición body→outro: fade out del duck, fade in del full (300ms)
        if len(body) > XFADE and len(outro) >= XFADE:
            body_xfade = body[-XFADE:].fade(to_gain=outro_gain - jingle_duck_db, start=0, duration=XFADE)
            body = body[:-XFADE] + body_xfade

        # ── Construir pista completa de jingle ───────────────────────────
        jingle_track = intro + body + outro

        # ── Overlay: voz sobre jingle (voz empieza en jingle_intro_ms) ───
        mixed = jingle_track.overlay(voice, position=jingle_intro_ms)

        # ── Normalización final broadcast (-14 LUFS ≈ -14 dBFS RMS) ─────
        mixed = _normalize_loudness(mixed, -14.0)

        # ── Exportar como OGG Opus (formato nativo WhatsApp voice note) ──
        out = io.BytesIO()
        mixed.export(out, format="ogg", codec="libopus", bitrate="128k")
        return out.getvalue()

    except Exception as e:
        import logging
        logging.getLogger(__name__).error("[MIX ERROR] %s", e)
        return voice_bytes


async def generate_radio_ad(
    business_name: str,
    message_or_intent: str,
    country: str = "mx",
    jingle_path: str | None = None,
    _script: str | None = None,
    mode: str = "classic",  # "classic" | "comunitaria"
    business_category: str | None = None,
) -> str:
    """
    Pipeline completo: guión → voz → mezcla → R2 → URL pública.
    Si se provee _script, se omite la llamada a Claude.
    business_category: categoría del negocio para elegir el jingle automáticamente.
    Retorna la URL del archivo de audio en R2.
    """
    # 1. Generar guión con Claude (o usar el provisto)
    script = _script or await generate_radio_script(business_name, message_or_intent, country, mode=mode)

    # 2. Sintetizar voz
    voice = LOCUTOR_VOICES.get(country, LOCUTOR_VOICES["default"])
    mp3_bytes = await text_to_speech(script, voice)

    # 3. Elegir jingle: prioridad jingle_path explícito > por categoría > sin jingle
    resolved_jingle = jingle_path or get_jingle_path(business_category)

    # 4. Mezclar voz + jingle
    audio_bytes = mix_with_jingle(mp3_bytes, resolved_jingle)

    # 4. Subir a R2
    ext = "ogg" if audio_bytes[:4] == b"OggS" else "mp3"
    key = f"radio/{business_name.lower().replace(' ', '_')}_{os.urandom(4).hex()}.{ext}"
    content_type = "audio/ogg" if ext == "ogg" else "audio/mpeg"
    url = await upload_bytes(audio_bytes, key, content_type=content_type)

    if not url:
        raise RuntimeError("No se pudo subir el audio a R2. Verifica las variables CF_R2_*.")

    return url
