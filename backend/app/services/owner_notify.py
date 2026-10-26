"""Avisos de pedido y cita al dueño (docs/specs/2026-10-23-avisos-al-dueno-por-central.md).

Primero por el WhatsApp propio del negocio. Si no lo tiene conectado, o Meta
rechaza el aviso (el dueño no le escribió a su número en 24 h), sale por el
número central de IaRadio: texto libre dentro de la ventana, y si no, la
plantilla utility que Meta cobra. Por eso el central lleva un tope diario por
negocio; al pasarlo va un último aviso y luego nada hasta el día siguiente.
"""
import logging
from datetime import datetime

from app.models.user import User
from app.services.availability_service import TZ

logger = logging.getLogger(__name__)

DAILY_CAP = 30
CAP_NOTICE = (
    "📋 Hoy ya te mandé {cap} avisos de pedidos y citas por aquí. Los que sigan llegando "
    "los ves en tu panel de IaRadio (Pedidos y Citas). Mañana te vuelvo a avisar por aquí 🙌"
)


def _key(advertiser: User) -> str:
    return f"owner_notify:{advertiser.id}:{datetime.now(TZ).date().isoformat()}"


async def _count_central(advertiser: User) -> int | None:
    """Cuántos avisos por el central lleva hoy (contando este). None si Redis
    no responde: el aviso sale igual, perder un pedido cuesta más que un aviso."""
    from app.core.redis import get_redis_optional

    redis = await get_redis_optional()
    if redis is None:
        return None
    try:
        key = _key(advertiser)
        n = await redis.incr(key)
        if n == 1:
            await redis.expire(key, 2 * 24 * 3600)
        return int(n)
    except Exception:
        logger.warning("[OWNER-NOTIFY] Redis falló, se manda sin contar", exc_info=True)
        return None


async def notify_owner(advertiser: User, body: str) -> str | None:
    """Manda `body` al celular del dueño. Devuelve por dónde salió ("own",
    "central", "cap") o None si no salió."""
    from app.services.meta_service import _connection, send_whatsapp
    from app.services.owner_question_service import owner_number
    from app.services.platform_whatsapp import platform_enabled, send_platform_text

    to = owner_number(advertiser)
    if not to:
        return None
    if _connection(advertiser) is not None:
        try:
            wamid, err = await send_whatsapp(to, body, advertiser=advertiser)
        except Exception as e:
            wamid, err = None, str(e)[:100]
        if wamid:
            return "own"
        logger.info("[OWNER-NOTIFY] advertiser=%s su WhatsApp no pudo (%s), va por el central", advertiser.id, err)

    if not platform_enabled():
        return None
    n = await _count_central(advertiser)
    if n is not None and n > DAILY_CAP + 1:
        return None
    capped = n == DAILY_CAP + 1
    message = CAP_NOTICE.format(cap=DAILY_CAP) if capped else body
    try:
        wamid, err = await send_platform_text(to, message)
    except Exception as e:
        wamid, err = None, str(e)[:100]
    if not wamid:
        logger.warning("[OWNER-NOTIFY] advertiser=%s no se pudo avisar por el central: %s", advertiser.id, err)
        return None
    return "cap" if capped else "central"
