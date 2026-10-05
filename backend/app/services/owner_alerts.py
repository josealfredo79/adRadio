"""Avisos al dueño por el número central de IaRadio cuando pasa algo en la web
que él tiene que atender: un cliente le escribe con el bot pausado, o llega
un cliente nuevo por el QR del mostrador o el directorio (/mi).

Diseñado para NO saturar al dueño (análisis 2026-10-04):
- Un aviso por cliente cada 30 min: si sigue escribiendo, ese aviso lo cubre.
- Máximo 4 avisos por hora por negocio; lo demás se junta en el siguiente.
- Clientes nuevos agrupados: un aviso cada 2 h como máximo, con los nombres.
- Silencio de 9 pm a 8 am (hora de México): se guarda todo y a las 8 llega
  un solo resumen (send_morning_digests, Celery Beat).
- Sin "Tu WhatsApp personal" en Configuración o sin número central, nada:
  igual lo ve en el Inbox.

Lo pendiente vive en Redis (sets de nombres por negocio), nunca en la BD.
"""
import logging
import uuid
from datetime import datetime

from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

WEB_MESSAGE_COOLDOWN = 30 * 60
NEW_CUSTOMER_COOLDOWN = 2 * 3600
MAX_ALERTS_PER_HOUR = 4
QUIET_FROM_HOUR = 21  # 9 pm
QUIET_UNTIL_HOUR = 8  # 8 am
PENDING_TTL = 2 * 24 * 3600

PENDING_WEB = "owner_pending_web:"
PENDING_NEW = "owner_pending_new:"


def _now_local() -> datetime:
    from app.services.availability_service import TZ

    return datetime.now(TZ)


def is_quiet_hours(now: datetime | None = None) -> bool:
    hour = (now or _now_local()).hour
    return hour >= QUIET_FROM_HOUR or hour < QUIET_UNTIL_HOUR


def _inbox_url() -> str:
    return f"{(settings.FRONTEND_URL or 'https://www.iaradio.online').rstrip('/')}/app/inbox"


def _names(values: set[str], limit: int = 5) -> str:
    names = sorted(values)
    shown = ", ".join(names[:limit])
    return shown + (f" y {len(names) - limit} más" if len(names) > limit else "")


def _destination(advertiser: User) -> str | None:
    from app.services.owner_question_service import owner_number
    from app.services.platform_whatsapp import platform_enabled

    return owner_number(advertiser) if platform_enabled() else None


async def _pop_pending(redis, advertiser_id) -> tuple[set[str], set[str]]:
    web = set(await redis.smembers(f"{PENDING_WEB}{advertiser_id}") or [])
    new = set(await redis.smembers(f"{PENDING_NEW}{advertiser_id}") or [])
    await redis.delete(f"{PENDING_WEB}{advertiser_id}", f"{PENDING_NEW}{advertiser_id}")
    return web, new


async def _remember(redis, key: str, advertiser_id, name: str) -> None:
    await redis.sadd(f"{key}{advertiser_id}", name)
    await redis.expire(f"{key}{advertiser_id}", PENDING_TTL)


async def _under_hourly_cap(redis, advertiser_id) -> bool:
    key = f"owner_alerts_hour:{advertiser_id}:{_now_local():%Y%m%d%H}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 3600)
    return count <= MAX_ALERTS_PER_HOUR


def _extras(web: set[str], new: set[str]) -> str:
    parts = []
    if web:
        parts.append(f"{len(web)} {'cliente más te escribió' if len(web) == 1 else 'clientes más te escribieron'} por la web ({_names(web)})")
    if new:
        parts.append(f"{len(new)} {'cliente nuevo' if len(new) == 1 else 'clientes nuevos'} ({_names(new)})")
    return f"\n\nAdemás: {' y '.join(parts)}." if parts else ""


async def _send(advertiser: User, to: str, body: str) -> bool:
    from app.services.platform_whatsapp import send_platform_text

    try:
        wamid, error = await send_platform_text(to, body)
    except Exception:
        logger.exception("[OWNER-ALERT] send failed advertiser=%s", advertiser.id)
        return False
    if error:
        logger.warning("[OWNER-ALERT] not delivered advertiser=%s: %s", advertiser.id, error)
    return wamid is not None


async def alert_web_message(redis, advertiser: User, contact_id: uuid.UUID, name: str, text: str) -> bool:
    """Un cliente escribió por la web y el bot está pausado. True si salió un aviso."""
    to = _destination(advertiser)
    if redis is None or not to:
        return False
    try:
        if not await redis.set(f"owner_alert_web:{contact_id}", "1", nx=True, ex=WEB_MESSAGE_COOLDOWN):
            return False  # ya se le avisó de este cliente hace menos de 30 min
        if is_quiet_hours() or not await _under_hourly_cap(redis, advertiser.id):
            await _remember(redis, PENDING_WEB, advertiser.id, name)
            return False
        web, new = await _pop_pending(redis, advertiser.id)
        web.discard(name)
    except Exception:
        logger.warning("[OWNER-ALERT] redis failed advertiser=%s", advertiser.id, exc_info=True)
        return False
    snippet = " ".join((text or "").split())[:200]
    body = (
        f"💬 {name} te escribió por la web:\n«{snippet}»"
        f"{_extras(web, new)}\n\nContéstale desde tu Inbox: {_inbox_url()}"
    )
    return await _send(advertiser, to, body)


async def alert_bot_down(redis, advertiser: User) -> bool:
    """Ningún modelo de IA contestó (llm_client: gratis y Claude): el cliente
    recibió "dame un momento". Se avisa al dueño una vez por hora como mucho,
    para que conteste él desde el Inbox."""
    to = _destination(advertiser)
    if redis is None or not to:
        return False
    if not await redis.set(f"owner_alert_bot_down:{advertiser.id}", "1", ex=3600, nx=True):
        return False
    return await _send(advertiser, to, (
        "⚠️ Tu bot no pudo contestar un mensaje (la IA no respondió). Le dijimos al cliente que en un momento "
        f"le contestas. Revisa tu Inbox: {_inbox_url()}"
    ))


async def alert_new_customer(redis, advertiser: User, name: str, via: str) -> bool:
    """Se unió un cliente nuevo por el QR o el directorio. True si salió un aviso."""
    to = _destination(advertiser)
    if redis is None or not to:
        return False
    label = f"{name} ({via})"
    try:
        if is_quiet_hours() or not await redis.set(
            f"owner_alert_new:{advertiser.id}", "1", nx=True, ex=NEW_CUSTOMER_COOLDOWN
        ):
            await _remember(redis, PENDING_NEW, advertiser.id, label)
            return False
        if not await _under_hourly_cap(redis, advertiser.id):
            await _remember(redis, PENDING_NEW, advertiser.id, label)
            return False
        web, new = await _pop_pending(redis, advertiser.id)
    except Exception:
        logger.warning("[OWNER-ALERT] redis failed advertiser=%s", advertiser.id, exc_info=True)
        return False
    new.add(label)
    if len(new) == 1:
        body = f"🎉 Cliente nuevo: {name} se unió desde {via}."
    else:
        body = f"🎉 {len(new)} clientes nuevos: {_names(new)}."
    body += _extras(web, set()) + f"\n\nVe tus contactos: {_inbox_url().replace('/inbox', '/contacts')}"
    return await _send(advertiser, to, body)


async def send_morning_digests(db, redis) -> int:
    """Celery Beat, 8 am: un solo resumen por negocio con lo que quedó
    guardado (silencio nocturno, tope por hora, clientes nuevos agrupados)."""
    from sqlalchemy import select

    ids: set[str] = set()
    for prefix in (PENDING_WEB, PENDING_NEW):
        async for key in redis.scan_iter(match=f"{prefix}*"):
            ids.add(str(key).split(":", 1)[1])
    sent = 0
    for advertiser_id in ids:
        try:
            advertiser = (await db.execute(select(User).where(User.id == uuid.UUID(advertiser_id)))).scalar_one_or_none()
        except ValueError:
            continue
        web, new = await _pop_pending(redis, advertiser_id)
        to = _destination(advertiser) if advertiser else None
        if not to or not (web or new):
            continue
        lines = ["☀️ Buenos días. Mientras estabas fuera:"]
        if web:
            lines.append(f"• {len(web)} {'cliente te escribió' if len(web) == 1 else 'clientes te escribieron'} por la web: {_names(web)}")
        if new:
            lines.append(f"• {len(new)} {'cliente nuevo' if len(new) == 1 else 'clientes nuevos'}: {_names(new)}")
        lines.append(f"\nRevísalo en tu Inbox: {_inbox_url()}")
        if await _send(advertiser, to, "\n".join(lines)):
            sent += 1
    return sent
