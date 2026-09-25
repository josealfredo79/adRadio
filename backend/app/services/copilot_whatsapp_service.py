"""
Copiloto por WhatsApp — el dueño opera su negocio escribiéndole al número
central de IaRadio ("¿cuántas citas tengo mañana?", "manda la promo 2x1 a
todos"), sin abrir el dashboard.

Es el mismo Copiloto del panel (copilot_service.handle_chat / handle_confirm,
mismas herramientas y mismos guardrails); aquí solo cambia el transporte:
- el historial vive en Redis por dueño (el panel lo manda el navegador);
- la tarjeta de confirmación del panel se vuelve botones "Sí, hazlo" /
  "Cancelar", y el dueño también puede contestar tecleando "sí" o "no".
"""
import json
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis_optional
from app.models.user import User
from app.services.copilot_service import handle_chat, handle_confirm
from app.services.platform_whatsapp import send_platform_buttons, send_platform_text

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


async def handle_owner_command(db: AsyncSession, *, owner: User, from_number: str, text: str) -> None:
    redis = await get_redis_optional()
    state = await _load(redis, owner)

    pending = state.get("pending")
    if pending:
        decision = parse_decision(text)
        if decision is not None:
            state["pending"] = None
            try:
                result = await handle_confirm(db, owner, pending, decision, redis=redis)
                reply = result["reply"]
            except ValueError as e:
                # Token expirado (5 min) o ya usado — el mismo mensaje que da el panel.
                reply = str(e)
            state["history"] += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
            await _save(redis, owner, state)
            await send_platform_text(from_number, reply)
            return
        # Escribió otra cosa en vez de confirmar: la acción pendiente se descarta
        # (nunca se ejecuta algo que el dueño no confirmó explícitamente).
        state["pending"] = None

    result = await handle_chat(db, owner, text, state["history"], channel="whatsapp")
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
    await send_platform_text(from_number, reply)
