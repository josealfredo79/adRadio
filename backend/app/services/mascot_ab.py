"""Prueba A/B de la mascota en la página pública (/sitio/{slug}): ¿la
mascota 3D animada hace que más visitantes abran el chat y agenden que la
misma mascota en imagen fija? (pedido del dueño 2026-10-05).

Cada visitante cae en una variante (la decide su navegador y la recuerda) y
se cuenta cada evento UNA vez por visitante, en Redis: sin tabla nueva y sin
datos personales — el visitante es un id aleatorio del navegador."""
import re
from datetime import datetime, timezone

VARIANTS = ("3d", "static")
# view: abrió la página · chat_open: abrió el chat · message: escribió algo ·
# confirmed: quedó una cita/pedido (respuesta ✅) · whatsapp: se fue a WhatsApp.
EVENTS = ("view", "chat_open", "message", "confirmed", "whatsapp")
PREFIX = "ab:mascot:"
SEEN_TTL = 60 * 60 * 24 * 60
_VISITOR_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_SLUG_RE = re.compile(r"^[a-z0-9-]{1,60}$")


def valid(slug: str, variant: str, event: str, visitor: str) -> bool:
    return (variant in VARIANTS and event in EVENTS
            and bool(_VISITOR_RE.match(visitor or "")) and bool(_SLUG_RE.match(slug or "")))


async def record(redis, slug: str, variant: str, event: str, visitor: str) -> bool:
    """Cuenta el evento si este visitante no lo había hecho en este sitio.
    Devuelve si contó."""
    if not await redis.set(f"{PREFIX}seen:{slug}:{visitor}:{event}", variant, ex=SEEN_TTL, nx=True):
        return False
    await redis.set(f"{PREFIX}since", datetime.now(timezone.utc).date().isoformat(), nx=True)
    await redis.hincrby(f"{PREFIX}total:{variant}", event, 1)
    await redis.hincrby(f"{PREFIX}site:{slug}:{variant}", event, 1)
    return True


def _pct(n: int, views: int) -> float:
    return round(100 * n / views, 1) if views else 0.0


def _decode(raw: dict) -> dict[str, int]:
    out = {}
    for k, v in (raw or {}).items():
        k = k.decode() if isinstance(k, bytes) else k
        out[k] = int(v)
    return out


async def results(redis) -> dict:
    """Totales por variante y las tasas que importan (sobre visitantes)."""
    since = await redis.get(f"{PREFIX}since")
    variants = {}
    for variant in VARIANTS:
        counts = {e: 0 for e in EVENTS} | _decode(await redis.hgetall(f"{PREFIX}total:{variant}"))
        views = counts["view"]
        variants[variant] = {
            "counts": counts,
            "chat_open_pct": _pct(counts["chat_open"], views),
            "message_pct": _pct(counts["message"], views),
            "confirmed_pct": _pct(counts["confirmed"], views),
            "whatsapp_pct": _pct(counts["whatsapp"], views),
        }
    return {"since": since.decode() if isinstance(since, bytes) else since, "variants": variants}
