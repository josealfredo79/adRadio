"""
Copiloto por WhatsApp — el dueño opera su negocio escribiéndole al número
central de IaRadio ("¿cuántas citas tengo mañana?", "manda la promo 2x1 a
todos"), sin abrir el dashboard.

Es el mismo Copiloto del panel (copilot_service.handle_chat / handle_confirm,
mismas herramientas y mismos guardrails); aquí solo cambia el transporte:
- el historial vive en Redis por dueño (el panel lo manda el navegador);
- la tarjeta de confirmación del panel se vuelve botones "Sí, hazlo" /
  "Cancelar", y el dueño también puede contestar tecleando "sí" o "no".

Cero fricción ("Habla con IaRadio" por WhatsApp):
- si el dueño manda una nota de voz, se le contesta con nota de voz (mismo
  número de mensajes que un texto; respuestas cortas, como en la web);
- una foto con texto ("tinte a 450") va directo al Copiloto; una foto sola se
  guarda y la siguiente instrucción la usa ("agrega este producto").
"""
import asyncio
import io
import json
import logging
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis_optional
from app.models.user import User
from app.services.copilot_business_tools import PHOTO_KEY_PREFIX
from app.services.copilot_service import handle_chat, handle_confirm
from app.services.platform_whatsapp import (
    send_platform_audio,
    send_platform_buttons,
    send_platform_text,
)
from app.services.storage_service import upload_bytes

logger = logging.getLogger(__name__)

_STATE_TTL_SECONDS = 24 * 3600
_MAX_HISTORY = 12

CONFIRM_BUTTONS = [("copilot_yes", "✅ Sí, hazlo"), ("copilot_no", "❌ Cancelar")]

_YES = {"si", "sí", "si hazlo", "sí hazlo", "hazlo", "ok", "okay", "dale", "va", "confirmo", "claro", "adelante", "de acuerdo"}
_NO = {"no", "cancelar", "cancela", "mejor no", "no gracias", "detente"}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\sáéíóúñ]", " ", text.lower())).strip()


def parse_decision(text: str) -> bool | None:
    """True = confirma, False = cancela, None = es otro mensaje."""
    t = _normalize(text)
    if t in _YES:
        return True
    if t in _NO:
        return False
    return None


def _key(owner: User) -> str:
    return f"copilot_wa:{owner.id}"


async def _load(redis, owner: User) -> dict:
    if redis is None:
        return {"history": [], "pending": None}
    try:
        raw = await redis.get(_key(owner))
        return json.loads(raw) if raw else {"history": [], "pending": None}
    except Exception:
        logger.warning("[COPILOT WA] Could not load state for %s", owner.id, exc_info=True)
        return {"history": [], "pending": None}


async def _save(redis, owner: User, state: dict) -> None:
    if redis is None:
        return
    state["history"] = state["history"][-_MAX_HISTORY:]
    try:
        await redis.set(_key(owner), json.dumps(state), ex=_STATE_TTL_SECONDS)
    except Exception:
        logger.warning("[COPILOT WA] Could not save state for %s", owner.id, exc_info=True)


async def has_pending_confirmation(owner: User) -> bool:
    state = await _load(await get_redis_optional(), owner)
    return bool(state.get("pending"))


PHOTO_MIME = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_PHOTO_PROMPT = "¡Buena foto! 📸 ¿Qué producto es y en cuánto lo vendes? Por ejemplo: *tinte, 450 pesos*."


def _speakable(text: str) -> str:
    text = re.sub(r"[*_~`#>]", "", text)
    text = re.sub(r"^\s*[-•]\s*", "", text, flags=re.MULTILINE)
    return " ".join(text.split())[:600]


def _to_ogg(mp3: bytes) -> bytes:
    """MP3 → OGG/Opus: el formato que WhatsApp muestra como nota de voz."""
    from pydub import AudioSegment

    out = io.BytesIO()
    AudioSegment.from_file(io.BytesIO(mp3), format="mp3").export(out, format="ogg", codec="libopus", bitrate="48k")
    return out.getvalue()


async def _voice_note_url(owner: User, text: str) -> str | None:
    """La respuesta dicha con la voz de IaRadio, subida para mandarla por link."""
    from app.services.radio.tts import _tts_edge

    try:
        mp3 = await _tts_edge(_speakable(text), "es-MX-DaliaNeural", rate="+0%", pitch="+0Hz")
        ogg = await asyncio.to_thread(_to_ogg, mp3)
        return await upload_bytes(ogg, f"copilot_voice/{owner.id}/{uuid.uuid4()}.ogg", "audio/ogg")
    except Exception:
        logger.warning("[COPILOT WA] voice reply failed for %s", owner.id, exc_info=True)
        return None


async def _reply(owner: User, to: str, text: str, voice: bool) -> None:
    """Contesta como le hablaron: nota de voz si mandó nota de voz (si algo
    falla, en texto)."""
    if voice:
        url = await _voice_note_url(owner, text)
        if url:
            wamid, _ = await send_platform_audio(to, url)
            if wamid:
                return
    await send_platform_text(to, text)


async def save_owner_photo(owner: User, content: bytes, mime: str) -> str | None:
    """Guarda la foto que el dueño mandó por WhatsApp donde el Copiloto acepta
    fotos de producto (copilot_business_tools._own_photo)."""
    ext = PHOTO_MIME.get(mime.split(";")[0])
    if not ext or not content or len(content) > 5 * 1024 * 1024:
        return None
    key = PHOTO_KEY_PREFIX.format(user_id=owner.id) + f"{uuid.uuid4()}.{ext}"
    return await upload_bytes(content, key, mime.split(";")[0])


async def handle_owner_command(
    db: AsyncSession,
    *,
    owner: User,
    from_number: str,
    text: str,
    voice: bool = False,
    photo_url: str | None = None,
) -> None:
    redis = await get_redis_optional()
    state = await _load(redis, owner)

    if photo_url and not text.strip():
        # Foto sin texto: se guarda y se pregunta qué es; la siguiente
        # instrucción (escrita o hablada) la usa.
        state["photo"] = photo_url
        await _save(redis, owner, state)
        await send_platform_text(from_number, _PHOTO_PROMPT)
        return

    pending = state.get("pending")
    if pending:
        decision = parse_decision(text)
        if decision is not None:
            state["pending"] = None
            try:
                result = await handle_confirm(
                    db, owner, pending, decision, redis=redis, channel="voz" if voice else "whatsapp",
                )
                reply = result["reply"]
            except ValueError as e:
                # Token expirado (5 min) o ya usado — el mismo mensaje que da el panel.
                reply = str(e)
            state["history"] += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
            await _save(redis, owner, state)
            await _reply(owner, from_number, reply, voice)
            return
        # Escribió otra cosa en vez de confirmar: la acción pendiente se descarta
        # (nunca se ejecuta algo que el dueño no confirmó explícitamente).
        state["pending"] = None

    message = text
    photo = photo_url or state.pop("photo", None)
    if photo:
        message = f"{text}\n[Foto adjunta: {photo}]"
    result = await handle_chat(db, owner, message, state["history"], channel="voz" if voice else "whatsapp")
    reply = result.get("reply") or "Listo."
    state["history"] += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]

    confirmation = result.get("pending_confirmation")
    if confirmation and redis is None:
        # Sin Redis no hay dónde guardar la confirmación entre mensajes.
        await _save(redis, owner, state)
        await send_platform_text(
            from_number,
            f"{reply}\n\nAhorita no puedo confirmar acciones por aquí — hazlo desde el Copiloto del panel, por favor.",
        )
        return

    if confirmation:
        state["pending"] = confirmation["confirmation_id"]
        await _save(redis, owner, state)
        await send_platform_buttons(from_number, reply, CONFIRM_BUTTONS)
        return

    await _save(redis, owner, state)
    await _reply(owner, from_number, reply, voice)
