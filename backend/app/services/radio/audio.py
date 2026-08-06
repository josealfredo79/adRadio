"""
Audio processing and mixing for radio ads.
"""

import io
import logging
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

JINGLES_DIR = Path(__file__).parent.parent.parent / "static" / "jingles"
SFX_DIR = Path(__file__).parent.parent.parent / "static" / "sfx"

SFX_FILES: dict[str, str] = {
    "ding": "sfx_ding.mp3",
    "whoosh": "sfx_whoosh.mp3",
    "coin": "sfx_coin.mp3",
}

# Qué efecto usar según el modo de guión, y en qué punto del audio (fracción
# 0-1 de la duración de la VOZ, no del audio final con jingle). Solo se
# asignan modos cuyo prompt (ver scripts.py) escribe una pausa/quiebre
# explícito en el guión en ese punto — no es una detección real de silencio,
# es una aproximación basada en la estructura de segundos que cada prompt
# ya declara. "ding" es universal: no depende del guión, es solo el sting
# de apertura bajo el intro del jingle.
SFX_MODE_EVENTS: dict[str, tuple[str, float]] = {
    # capsula/comunitaria: guión tiene "... Este dato/momento te lo trae..."
    # justo antes de la mención del negocio, ~mitad del guión.
    "capsula": ("whoosh", 0.50),
    "comunitaria": ("whoosh", 0.50),
    # trivia: "... La respuesta es..." — el momento de premio/revelación,
    # después de la pregunta (8-10s) + pausa (2-3s) de ~30s totales.
    "trivia": ("coin", 0.38),
}


def resolve_sfx_events(mode: str, voice_len_ms: int) -> list[tuple[str, int]]:
    """Decide qué efectos usar y en qué posición (ms, timeline de la voz)
    según el modo de guión. Devuelve [] si el modo no tiene un punto de
    quiebre reconocido — mejor omitir el efecto que adivinar mal."""
    events: list[tuple[str, int]] = [("ding", 0)]
    mode_event = SFX_MODE_EVENTS.get(mode)
    if mode_event:
        sfx_name, fraction = mode_event
        events.append((sfx_name, int(voice_len_ms * fraction)))
    return events


def _overlay_sfx(track: "AudioSegment", sfx_name: str, position_ms: int, gain_db: float = -9.0) -> "AudioSegment":  # type: ignore[name-defined]
    """Superpone un efecto corto sobre `track` en `position_ms`, a un volumen
    bajo el de la voz/jingle para que acentúe sin taparlos."""
    path = SFX_DIR / SFX_FILES.get(sfx_name, "")
    if not path.exists():
        logger.warning("[RADIO] SFX file not found: %s", sfx_name)
        return track
    from pydub import AudioSegment  # type: ignore

    sfx = AudioSegment.from_mp3(path)
    sfx = _normalize_loudness(sfx, gain_db)
    position_ms = max(0, min(position_ms, max(0, len(track) - 1)))
    return track.overlay(sfx, position=position_ms)


def _norm(s: str) -> str:
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower().strip()


CATEGORY_JINGLE_MAP: dict[str, str] = {
    "inmobiliaria": "inmobiliaria.mp3",
    "bienes raices": "inmobiliaria.mp3",
    "terrenos": "inmobiliaria.mp3",
    "construccion": "inmobiliaria.mp3",
    "arquitectura": "inmobiliaria.mp3",
    "restaurante": "restaurante.mp3",
    "comida": "restaurante.mp3",
    "food": "restaurante.mp3",
    "cafeteria": "restaurante.mp3",
    "taqueria": "restaurante.mp3",
    "panaderia": "restaurante.mp3",
    "pasteleria": "restaurante.mp3",
    "pizzeria": "restaurante.mp3",
    "tienda": "tienda.mp3",
    "retail": "tienda.mp3",
    "ropa": "tienda.mp3",
    "moda": "tienda.mp3",
    "boutique": "tienda.mp3",
    "ferreteria": "tienda.mp3",
    "herramientas": "tienda.mp3",
    "abarrotes": "tienda.mp3",
    "supermercado": "tienda.mp3",
    "tecnologia": "tecnologia.mp3",
    "tech": "tecnologia.mp3",
    "software": "tecnologia.mp3",
    "electronica": "tecnologia.mp3",
    "informatica": "tecnologia.mp3",
    "celulares": "tecnologia.mp3",
    "salud": "salud.mp3",
    "medico": "salud.mp3",
    "farmacia": "salud.mp3",
    "bienestar": "salud.mp3",
    "spa": "salud.mp3",
    "clinica": "salud.mp3",
    "dental": "salud.mp3",
    "veterinaria": "salud.mp3",
    "belleza": "belleza.mp3",
    "estetica": "belleza.mp3",
    "salon": "belleza.mp3",
    "peluqueria": "belleza.mp3",
    "cosmeticos": "belleza.mp3",
    "barberia": "belleza.mp3",
    "unas": "belleza.mp3",
    "deportes": "deportes.mp3",
    "gimnasio": "deportes.mp3",
    "gym": "deportes.mp3",
    "fitness": "deportes.mp3",
    "deporte": "deportes.mp3",
    "yoga": "deportes.mp3",
    "crossfit": "deportes.mp3",
    "educacion": "educacion.mp3",
    "escuela": "educacion.mp3",
    "academia": "educacion.mp3",
    "colegio": "educacion.mp3",
    "universidad": "educacion.mp3",
    "cursos": "educacion.mp3",
    "tutoria": "educacion.mp3",
    "idiomas": "educacion.mp3",
    "automotriz": "automotriz.mp3",
    "autos": "automotriz.mp3",
    "carros": "automotriz.mp3",
    "taller": "automotriz.mp3",
    "mecanica": "automotriz.mp3",
    "agencia": "automotriz.mp3",
    "refacciones": "automotriz.mp3",
    "llantas": "automotriz.mp3",
    "corporativo": "corporativo.mp3",
    "servicios": "corporativo.mp3",
    "empresa": "corporativo.mp3",
    "consultoria": "corporativo.mp3",
    "juridico": "corporativo.mp3",
    "contabilidad": "corporativo.mp3",
    "seguros": "corporativo.mp3",
}

JINGLE_DEFAULT = "generico.mp3"


def get_jingle_path(business_category: str | None, day_variant: int = 0) -> str | None:
    """Retorna la ruta al jingle según la categoría del negocio."""
    if not business_category:
        filename = JINGLE_DEFAULT
    else:
        cat = _norm(business_category)
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


def _normalize_loudness(segment, target_dbfs: float = -16.0):
    diff = target_dbfs - segment.dBFS
    return segment.apply_gain(diff)


def _apply_peak_ceiling(segment, ceiling_db: float = -2.0):
    """Limitador de techo: `_normalize_loudness` ajusta ganancia por RMS
    (volumen promedio), no por pico — con compresión de por medio eso puede
    dejar picos por encima de 0dBFS y clipear. Si el pico excede el techo,
    baja la ganancia lo justo para no saturar.

    -2.0dB (no -1.0) porque la exportación a Opus (lossy) puede rebasar el
    pico de muestra pre-encode por "true peak overshoot" — verificado
    empíricamente: con efectos de sonido (transitorios más agresivos que la
    voz) -1.0dB seguía clipeando tras re-decodificar el .ogg, -2.0dB no."""
    if segment.max_dBFS > ceiling_db:
        segment = segment.apply_gain(ceiling_db - segment.max_dBFS)
    return segment


def _process_voice(voice: "AudioSegment") -> "AudioSegment":  # type: ignore[name-defined]
    try:
        from pydub.effects import high_pass_filter, normalize, compress_dynamic_range  # type: ignore

        voice = high_pass_filter(voice, cutoff=120)
        # Compresión tipo locutor de radio: pareja el volumen entre sílabas
        # fuertes/débiles antes de normalizar, para que suene "pegada" al
        # micrófono en vez de con la dinámica cruda del TTS.
        voice = compress_dynamic_range(voice, threshold=-20.0, ratio=4.0, attack=5.0, release=50.0)
        voice = normalize(voice)
        voice = voice + 2.5
        return voice
    except Exception:
        logger.warning("[RADIO] Audio processing failed, returning unprocessed voice", exc_info=True)
        return voice


def mix_with_jingle(
    voice_bytes: bytes,
    jingle_path: str | None = None,
    jingle_intro_ms: int = 2500,
    jingle_outro_ms: int = 2000,
    jingle_fade_out_ms: int = 1800,
    jingle_full_db: float = -12.0,
    jingle_duck_db: float = -22.0,
    voice_target_dbfs: float = -10.0,
    jingle_offset_ratio: float = 0.0,
    include_sfx: bool = False,
    mode: str = "classic",
) -> bytes:
    """
    Mezcla profesional de radio con ducking automático.
    """
    try:
        from pydub import AudioSegment  # type: ignore

        voice = AudioSegment.from_mp3(io.BytesIO(voice_bytes))
        voice = _process_voice(voice)
        diff = voice_target_dbfs - voice.dBFS
        voice = voice.apply_gain(diff)

        sfx_events = resolve_sfx_events(mode, len(voice)) if include_sfx else []

        if not jingle_path or not Path(jingle_path).exists():
            out = io.BytesIO()
            for sfx_name, position_ms in sfx_events:
                voice = _overlay_sfx(voice, sfx_name, position_ms)
            voice = _normalize_loudness(voice, -14.0)
            voice = _apply_peak_ceiling(voice)
            voice.export(out, format="ogg", codec="libopus", bitrate="128k")
            return out.getvalue()

        jingle_raw = AudioSegment.from_file(jingle_path)

        total_needed_ms = jingle_intro_ms + len(voice) + jingle_outro_ms + jingle_fade_out_ms

        # Rotar el punto de inicio del jingle para dar variedad entre días
        offset_ms = int(len(jingle_raw) * jingle_offset_ratio) if jingle_offset_ratio > 0 else 0
        if offset_ms + total_needed_ms > len(jingle_raw):
            offset_ms = 0

        if len(jingle_raw) < total_needed_ms:
            loops = total_needed_ms // len(jingle_raw) + 2
            jingle_raw = jingle_raw * loops

        jingle_raw = jingle_raw[offset_ms:offset_ms + total_needed_ms]

        jingle_raw = _normalize_loudness(jingle_raw, -14.0)

        intro  = jingle_raw[:jingle_intro_ms]
        body   = jingle_raw[jingle_intro_ms : jingle_intro_ms + len(voice)]
        outro  = jingle_raw[jingle_intro_ms + len(voice) : jingle_intro_ms + len(voice) + jingle_outro_ms + jingle_fade_out_ms]

        intro_gain  = jingle_full_db - intro.dBFS
        intro       = intro.apply_gain(intro_gain)

        body_gain   = jingle_duck_db - body.dBFS
        body        = body.apply_gain(body_gain)

        XFADE = 300
        if len(intro) > XFADE:
            intro_xfade = intro[-XFADE:].fade(to_gain=body_gain - jingle_full_db, start=0, duration=XFADE)
            intro = intro[:-XFADE] + intro_xfade

        outro_gain  = jingle_full_db - outro.dBFS
        outro       = outro.apply_gain(outro_gain)
        outro       = outro.fade_out(jingle_fade_out_ms)

        if len(body) > XFADE and len(outro) >= XFADE:
            body_xfade = body[-XFADE:].fade(to_gain=outro_gain - jingle_duck_db, start=0, duration=XFADE)
            body = body[:-XFADE] + body_xfade

        jingle_track = intro + body + outro
        mixed = jingle_track.overlay(voice, position=jingle_intro_ms)

        for sfx_name, position_in_voice_ms in sfx_events:
            # "ding" es el sting de apertura: va bajo el intro del jingle,
            # antes de que empiece la voz. El resto están posicionados
            # relativos al inicio de la voz (jingle_intro_ms de offset).
            abs_position = position_in_voice_ms if sfx_name == "ding" else jingle_intro_ms + position_in_voice_ms
            mixed = _overlay_sfx(mixed, sfx_name, abs_position)

        # Compresión de bus (máster): controla los picos donde voz y jingle
        # se solapan en los crossfades, y sube el volumen percibido sin
        # clipear — el mismo tipo de procesamiento que aplica una consola
        # de radio a la salida final, no solo a la voz por separado.
        from pydub.effects import compress_dynamic_range  # type: ignore
        mixed = compress_dynamic_range(mixed, threshold=-16.0, ratio=2.5, attack=10.0, release=100.0)
        mixed = _normalize_loudness(mixed, -14.0)
        mixed = _apply_peak_ceiling(mixed)

        out = io.BytesIO()
        mixed.export(out, format="ogg", codec="libopus", bitrate="128k")
        return out.getvalue()

    except Exception as e:
        logger.error("[MIX ERROR] %s", e)
        return voice_bytes
