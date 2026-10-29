"""¿Para cuál negocio? — un dueño cuyo celular está en varias cuentas le
escribe al número central. Antes el Copiloto usaba la primera cuenta que
encontraba (la campaña del 29-oct salió desde IaRadio en vez de CityCell);
ahora pregunta con botones y recuerda la elección 12 h desde su último
mensaje (docs/specs/2026-10-29-para-cual-negocio.md).

En Redis: `central_owner:<número>` = id de la cuenta escogida, y
`central_pick:<número>` = lo que pidió mientras se le preguntaba, para
atenderlo en cuanto escoja sin que lo repita."""
import json
import logging
import re
import unicodedata

from app.models.user import User
from app.services.platform_whatsapp import send_platform_buttons, send_platform_list

logger = logging.getLogger(__name__)

CHOICE_KEY = "central_owner:{number}"
PICK_KEY = "central_pick:{number}"
CHOICE_TTL_SECONDS = 12 * 3600
PICK_TTL_SECONDS = 3600

ASK_TEXT = "Tienes varios negocios con este número 🏪 ¿Para cuál es?"
SWITCH = {"cambiar negocio", "cambiar de negocio", "otro negocio", "cambiar cuenta", "cambiar de cuenta"}


def _number(number: str) -> str:
    """Una sola forma por celular: sin '+' y sin el '1' móvil de México."""
    digits = number.lstrip("+").replace(" ", "")
    return "52" + digits[3:] if digits.startswith("521") else digits


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def is_switch(text: str) -> bool:
    return _norm(text) in SWITCH


def labels(owners: list[User]) -> list[str]:
    """Nombre de cada negocio para el botón; si dos se llaman igual, se numeran."""
    names = [(o.business_name or "").strip() or "Mi negocio" for o in owners]
    out: list[str] = []
    for i, name in enumerate(names):
        # Mismo nombre, o tan parecido que en el botón (20 letras) se ve igual.
        repeated = sum(1 for prev in names[:i] if _norm(prev[:20]) == _norm(name[:20]))
        out.append(f"{name[:16]} ({repeated + 1})" if repeated else name)
    return out


def match(owners: list[User], text: str, *, asking: bool = False) -> User | None:
    """La cuenta que tocó (el botón llega como `pick:<id>`) o que escribió por
    nombre. Un número solo cuenta mientras se le está preguntando: si no, "1"
    puede ser la respuesta a otra cosa."""
    raw = (text or "").strip()
    if raw.startswith("pick:"):
        return next((o for o in owners if str(o.id) == raw[5:]), None)
    said = _norm(raw)
    if not said:
        return None
    if said.isdigit():
        return owners[int(said) - 1] if asking and 1 <= int(said) <= len(owners) else None
    for owner, label in zip(owners, labels(owners)):
        if said in {_norm(label), _norm(label[:20]), _norm(label[:24])}:
            return owner
    return None


async def current(redis, number: str, owners: list[User]) -> User | None:
    """La cuenta escogida, si sigue vigente; cada mensaje renueva las 12 h."""
    key = CHOICE_KEY.format(number=_number(number))
    try:
        raw = await redis.get(key)
    except Exception:
        logger.warning("[CENTRAL PICK] Redis read failed", exc_info=True)
        return None
    chosen = next((o for o in owners if raw and str(o.id) == (raw.decode() if isinstance(raw, bytes) else raw)), None)
    if chosen is not None:
        await choose(redis, number, chosen)
    return chosen


async def choose(redis, number: str, owner: User) -> None:
    try:
        await redis.set(CHOICE_KEY.format(number=_number(number)), str(owner.id), ex=CHOICE_TTL_SECONDS)
    except Exception:
        logger.warning("[CENTRAL PICK] Redis write failed", exc_info=True)


async def forget(redis, number: str) -> None:
    try:
        await redis.delete(CHOICE_KEY.format(number=_number(number)))
    except Exception:
        logger.warning("[CENTRAL PICK] Redis delete failed", exc_info=True)


async def held(redis, number: str) -> dict | None:
    """Lo que pidió mientras se le preguntaba (None si no se le está preguntando)."""
    try:
        raw = await redis.get(PICK_KEY.format(number=_number(number)))
        return json.loads(raw) if raw else None
    except Exception:
        logger.warning("[CENTRAL PICK] Redis read failed", exc_info=True)
        return None


async def hold(redis, number: str, request: dict) -> None:
    """Guarda lo primero que pidió; si escribe otra cosa sin escoger, no lo pisa."""
    if await held(redis, number) is not None:
        return
    try:
        await redis.set(PICK_KEY.format(number=_number(number)), json.dumps(request), ex=PICK_TTL_SECONDS)
    except Exception:
        logger.warning("[CENTRAL PICK] Redis write failed", exc_info=True)


async def release(redis, number: str) -> None:
    try:
        await redis.delete(PICK_KEY.format(number=_number(number)))
    except Exception:
        logger.warning("[CENTRAL PICK] Redis delete failed", exc_info=True)


async def ask(to: str, owners: list[User]) -> None:
    names = labels(owners)
    if len(owners) <= 3:
        await send_platform_buttons(to, ASK_TEXT, [(f"pick:{o.id}", n[:20]) for o, n in zip(owners, names)])
    else:
        await send_platform_list(to, ASK_TEXT, [(f"pick:{o.id}", n[:24]) for o, n in zip(owners, names)],
                                 button_text="Ver negocios")


def chosen_text(owner: User) -> str:
    return f"Listo, ahora estás en *{(owner.business_name or 'tu negocio').strip()}* 🏪"
