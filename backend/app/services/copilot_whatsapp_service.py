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
    send_platform_image,
    send_platform_list,
    send_platform_text,
)
from app.services.storage_service import upload_bytes

logger = logging.getLogger(__name__)

_STATE_TTL_SECONDS = 24 * 3600
_MAX_HISTORY = 12

CONFIRM_BUTTONS = [("copilot_yes", "✅ Sí, hazlo"), ("copilot_no", "❌ Cancelar")]
# Una promo nueva (send_promo) trae además "Cambiar": el dueño corrige el mensaje antes de mandarlo.
PROMO_BUTTONS = [("copilot_yes", "✅ Sí, mándala"), ("copilot_edit", "✏️ Cambiar"), ("copilot_no", "❌ Cancelar")]
_EDIT = {"cambiar", "cambia", "cambiala", "cámbiala", "editar", "corregir"}
EDIT_PROMPT = "¿Qué le cambio? Dímelo con tus palabras, por ejemplo: *más corta*, *quítale el precio* o *que diga hasta el domingo*."

_YES = {"si", "sí", "si hazlo", "sí hazlo", "si mandala", "sí mándala", "sí mandala", "mandala", "mándala", "hazlo", "ok", "okay", "dale", "va", "confirmo", "claro", "adelante", "de acuerdo"}
_NO = {"no", "cancelar", "cancela", "mejor no", "no gracias", "detente"}

# La plática de campañas (campaign_builder) se puede dejar a medias: la
# campaña queda como borrador y se retoma después.
BUILDER_EXIT = {"salir", "cancelar", "cancela", "dejalo", "déjalo", "luego", "despues", "después"}
BUILDER_EXIT_TEXT = "Listo, la dejo guardada como borrador 👍 Cuando quieras seguimos."
BUILDER_INPUT_HINT = {
    "what": "Escríbelo o mándame una nota de voz.",
    "edit": "Escríbelo o mándame una nota de voz.",
    "photo": "Mándame una foto o toca una opción.",
    "contact": "Escribe su nombre o teléfono.",
}
BUILDER_PHOTO_HINT = "La foto la usamos cuando lleguemos al paso de la foto 📷."


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


async def has_open_builder(owner: User) -> bool:
    """La plática de campañas está abierta: lo que escriba es una respuesta del
    armador, aunque tenga preguntas de clientes pendientes."""
    state = await _load(await get_redis_optional(), owner)
    return bool(state.get("builder"))


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
    from app.services.radio.tts import speak_voice

    try:
        mp3 = await speak_voice(_speakable(text))
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


def _cut(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: max(1, limit - 1)].rstrip() + "…"


def _wa_title(step: dict, choice: dict, limit: int) -> str:
    if step.get("step") == "send":
        short = {"web": "Gratis por web", "whatsapp": "Por WhatsApp"}.get(choice["id"])
        if short:
            return short
    return _cut(choice["label"], limit)


def _match_choice(choices: list[dict], answer: str) -> str | None:
    """El título que WhatsApp devuelve es el que se envió (a veces recortado a
    20/24 letras); también acepta el nombre completo y el número de la lista."""
    norm = _normalize(answer)
    if not norm:
        return None
    for i, c in enumerate(choices, 1):
        label = c.get("label") or ""
        for candidate in (label, _cut(label, 20), _cut(label, 24), c.get("id") or ""):
            if candidate and _normalize(candidate) == norm:
                return c["id"]
        if norm == str(i):
            return c["id"]
    return None


# Lo que el dueño escribe en vez de tocar el botón (o cuando Meta rechazó los
# botones y le llegó el texto con las opciones).
_ALIASES = {
    "format": {"texto": "f:text", "text": "f:text", "mensaje": "f:text", "foto": "f:photo",
               "imagen": "f:photo", "cartel": "f:photo", "audio": "f:audio", "cuña": "f:audio",
               "cuna": "f:audio", "radio": "f:audio"},
    "style": {"anuncio": "s:radio", "cuña": "s:radio", "cuna": "s:radio", "consejo": "s:comunitaria",
              "comunitaria": "s:comunitaria", "dato": "s:capsula", "dato curioso": "s:capsula",
              "curiosidad": "s:capsula", "capsula": "s:capsula", "cápsula": "s:capsula",
              "trivia": "s:trivia", "historia": "s:historia", "aviso": "s:alerta", "alerta": "s:alerta",
              "temporada": "s:estacional", "estacional": "s:estacional", "de temporada": "s:estacional"},
    "audience": {"todos": "a:all", "all": "a:all", "compradores": "a:bought",
                 "los que compraron": "a:bought", "compraron": "a:bought", "uno": "a:one",
                 "un cliente": "a:one", "cliente": "a:one"},
    "photo": {"subir": "upload", "subir foto": "upload", "subir una foto": "upload",
              "mi foto": "upload", "foto": "upload", "otra foto": "upload",
              "cartel": "poster", "cartel de colores": "poster", "poster": "poster"},
    "preview": {"si": "ok", "sí": "ok", "ok": "ok", "okay": "ok", "dale": "ok", "va": "ok",
                "correcto": "ok", "esta bien": "ok", "está bien": "ok", "asi esta bien": "ok",
                "así está bien": "ok", "no": "other", "otra": "other", "otra version": "other",
                "otra versión": "other", "no me gusta": "other", "cambiar": "edit",
                "cambiar el texto": "edit", "editar": "edit"},
    # En "mandar" solo valen las frases completas: un "sí"/"también" suelto
    # puede ser la respuesta a un cliente y no debe disparar un envío pagado.
    "send": {"gratis por web": "web", "mandar gratis por web": "web", "por web": "web",
             "por whatsapp": "whatsapp", "también por whatsapp": "whatsapp",
             "tambien por whatsapp": "whatsapp"},
}


def _choice_for(step: dict, answer: str) -> str | None:
    ids = {c["id"] for c in (step.get("choices") or [])}
    norm = _normalize(answer)
    if step.get("step") == "send":
        alias = _ALIASES["send"].get(norm)
        if alias in ids:
            return alias
        if norm.startswith(("también por whatsapp", "tambien por whatsapp")) and "whatsapp" in ids:
            return "whatsapp"
        return None
    alias = _ALIASES.get(step.get("step"), {}).get(norm)
    if alias and alias in ids:
        return alias
    return _match_choice(step.get("choices") or [], answer)


async def _note_url(url: str) -> str:
    """La cuña se manda como nota de voz: si no está en OGG/Opus, se convierte
    (igual que las respuestas de voz). Si falla, se manda el audio tal cual."""
    if not url or url.lower().endswith((".ogg", ".opus")):
        return url
    try:
        import httpx

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        ogg = await asyncio.to_thread(_to_ogg, resp.content)
        saved = await upload_bytes(ogg, f"copilot_voice/{uuid.uuid4()}.ogg", "audio/ogg")
        return saved or url
    except Exception:
        logger.warning("[COPILOT WA] Could not turn campaign audio into a voice note", exc_info=True)
        return url


async def _send_question(to: str, step: dict) -> None:
    text = (step.get("text") or "").strip()
    if step.get("input"):
        hint = BUILDER_INPUT_HINT.get(step["input"])
        if hint:
            text = f"{text}\n\n{hint}"
    choices = step.get("choices") or []
    if not choices:
        await send_platform_text(to, text)
        return
    # El botón de WhatsApp solo cabe en 20 letras: el costo va en el texto.
    if step.get("step") == "send":
        for c in choices:
            if c["id"] == "whatsapp" and "(aprox" in c.get("label", ""):
                text = f"{text}\n{c['label']}."
    if len(choices) <= 3:
        await send_platform_buttons(to, text, [(c["id"], _wa_title(step, c, 20)) for c in choices])
    else:
        await send_platform_list(to, text, [(c["id"], _wa_title(step, c, 24)) for c in choices[:10]])


async def _render_step(owner: User, to: str, step: dict, state: dict, redis) -> None:
    """Dibuja un paso: primero la vista previa (cuña, imagen o texto) y luego
    la pregunta con botones/lista."""
    text = step.get("text") or ""
    preview = step.get("preview") or {}
    kind = preview.get("kind")
    if kind == "audio" and preview.get("audio_url"):
        url = await _note_url(preview["audio_url"])
        wamid, _ = await send_platform_audio(to, url)
        if not wamid:
            text = f"No pude mandarte la cuña por aquí; escúchala en el panel.\n\n{text}"
    elif kind == "image" and preview.get("image_url"):
        wamid, _ = await send_platform_image(to, preview["image_url"])
        if not wamid:
            text = f"No pude mandarte la imagen por aquí.\n\n{text}"
    elif kind == "text" and preview.get("text"):
        shown = preview["text"].strip()
        if shown and shown not in text:
            text = f"{shown}\n\n{text}"
    await _send_question(to, {**step, "text": text})
    if step.get("done"):
        state["builder"] = None
    else:
        # El paso "¿Qué quieres anunciar?" todavía no tiene campaña; se guarda
        # igual para no perder la plática (ej. "Empezar otra").
        state["builder"] = {**step, "text": text}
    if redis is not None:
        await _save(redis, owner, state)


async def _builder_turn(db: AsyncSession, owner: User, to: str, text: str, photo_url: str | None,
                        *, voice: bool, state: dict, redis) -> None:
    """Un mensaje del dueño mientras la plática de campañas está abierta."""
    from app.domain.campaign_builder import handle as build

    step = state["builder"]
    norm = _normalize(text)
    if norm in BUILDER_EXIT:
        state["builder"] = None
        state["history"] += [{"role": "user", "content": text},
                             {"role": "assistant", "content": BUILDER_EXIT_TEXT}]
        await _save(redis, owner, state)
        await _reply(owner, to, BUILDER_EXIT_TEXT, voice)
        return

    choice = None
    answer = (text or "").strip()
    if photo_url:
        if step.get("step") == "photo":
            choice, answer = "upload", photo_url
        elif not answer:
            await send_platform_text(to, BUILDER_PHOTO_HINT)
            await _send_question(to, step)
            return
    if choice is None and answer:
        choice = _choice_for(step, answer)
        if choice:
            answer = ""
    if choice == "upload" and not photo_url:
        await send_platform_text(to, "Mándame la foto que quieres usar 📷.")
        return
    if not choice and not answer:
        await _send_question(to, step)
        return

    cid = None if choice == "new" else step.get("campaign_id")
    result = await build(db, owner, campaign_id=cid, choice=choice, text=answer or None)
    said = "[foto]" if choice == "upload" else (text or "")
    state["history"] += [{"role": "user", "content": said},
                         {"role": "assistant", "content": result.get("text") or ""}]
    await _render_step(owner, to, result, state, redis)


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

    if state.get("builder"):
        # La plática de campañas está abierta: todo lo que escriba es una
        # respuesta (o "salir"). No pasa por la IA.
        await _builder_turn(db, owner, from_number, text, photo_url, voice=voice, state=state, redis=redis)
        return

    if photo_url and not text.strip():
        # Foto sin texto: se guarda y se pregunta qué es; la siguiente
        # instrucción (escrita o hablada) la usa.
        state["photo"] = photo_url
        await _save(redis, owner, state)
        await send_platform_text(from_number, _PHOTO_PROMPT)
        return

    pending = state.get("pending")
    if pending and _normalize(text) in _EDIT:
        # "Cambiar": no se manda nada; lo que diga después vuelve a armar la promo.
        state["pending"] = None
        state["history"] += [{"role": "user", "content": text}, {"role": "assistant", "content": EDIT_PROMPT}]
        await _save(redis, owner, state)
        await _reply(owner, from_number, EDIT_PROMPT, voice)
        return
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
    result = await handle_chat(
        db, owner, message, state["history"], channel="voz" if voice else "whatsapp", attached_photo=photo,
    )
    reply = result.get("reply") or "Listo."
    state["history"] += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]

    builder = next((a for a in (result.get("actions") or []) if a.get("tool") == "build_campaign"), None)
    if builder:
        if redis is None:
            await send_platform_text(
                from_number,
                f"{reply}\n\nPara armarla paso a paso necesito guardar la plática entre mensajes — "
                "hazlo desde el panel, por favor.",
            )
            return
        await _render_step(owner, from_number, builder["data"]["builder"], state, redis)
        return

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
        buttons = PROMO_BUTTONS if confirmation.get("tool") == "send_promo" else CONFIRM_BUTTONS
        await send_platform_buttons(from_number, reply, buttons)
        return

    await _save(redis, owner, state)
    await _reply(owner, from_number, reply, voice)
