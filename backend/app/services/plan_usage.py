"""Cuota de conversaciones del bot con IA — nuestro costo variable principal.

Una conversación = un cliente atendido por la IA dentro de una ventana de
24 h (como Meta cuenta las suyas), sin importar cuántos mensajes se crucen.
Se cuenta solo cuando de verdad se llama al modelo (RAG / respuesta libre);
los flujos deterministas (citas, pedidos, catálogo) no gastan IA y no cuentan.

Pasarse del límite NUNCA deja a un cliente sin respuesta: el bot sigue con un
modelo más económico (`economy=True` en llm_client). Un bot que se apaga le
cuesta al negocio una venta; uno que contesta un poco más simple, no.
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from app.core.plans import plan_limit
from app.services.availability_service import TZ

logger = logging.getLogger(__name__)

CONV_WINDOW_SECONDS = 24 * 3600
DEDUPE_PREFIX = "botconv:"
ALERT_LEVELS = (80, 100)


@dataclass
class ConversationUsage:
    used: int
    cap: int  # límite del plan + paquetes extra; -1 = sin límite
    economy: bool


def _current_month() -> str:
    return datetime.now(TZ).strftime("%Y-%m")


def _roll_month(user, month: str) -> None:
    """Cambio de mes: los paquetes extra que se usaron se descuentan del
    saldo de paquetes (lo no usado sigue disponible) y el contador vuelve a 0."""
    if user.bot_conv_month == month:
        return
    limit = plan_limit(user.current_plan, "conversations")
    if user.bot_conv_month and limit >= 0:
        consumed_extra = max(0, (user.bot_conv_used or 0) - limit)
        user.bot_conv_extra = max(0, (user.bot_conv_extra or 0) - consumed_extra)
    user.bot_conv_month = month
    user.bot_conv_used = 0
    user.bot_conv_alert = 0


def usage_snapshot(user) -> ConversationUsage:
    """Uso del mes sin modificar nada (para el dashboard)."""
    limit = plan_limit(user.current_plan, "conversations")
    month = _current_month()
    used = (user.bot_conv_used or 0) if user.bot_conv_month == month else 0
    if limit < 0:
        return ConversationUsage(used=used, cap=-1, economy=False)
    extra = user.bot_conv_extra or 0
    if user.bot_conv_month and user.bot_conv_month != month:
        extra = max(0, extra - max(0, (user.bot_conv_used or 0) - limit))
    cap = limit + extra
    return ConversationUsage(used=used, cap=cap, economy=used > cap)


async def register_bot_conversation(advertiser_id: uuid.UUID, conversation_key: str, redis) -> ConversationUsage:
    """Llamar justo antes de pedirle una respuesta a la IA. Cuenta una
    conversación nueva si este cliente no ha hablado con la IA en 24 h, manda
    los avisos de 80 % / 100 %, y dice si hay que usar el modelo económico.

    Usa su propia sesión con SELECT ... FOR UPDATE: el contador se guarda
    aunque el que llama no haga commit (ej. el chat web), y dos mensajes
    simultáneos no se pisan. Ante cualquier error, deja pasar con el modelo
    normal — la cuota nunca debe tumbar al bot."""
    from app.database import AsyncSessionLocal
    from app.models.user import User

    try:
        is_new = True
        if redis is not None:
            is_new = bool(await redis.set(
                f"{DEDUPE_PREFIX}{advertiser_id}:{conversation_key}", "1", ex=CONV_WINDOW_SECONDS, nx=True,
            ))
        async with AsyncSessionLocal() as db:
            user = await db.get(User, advertiser_id, with_for_update=True)
            if user is None:
                return ConversationUsage(used=0, cap=-1, economy=False)
            _roll_month(user, _current_month())
            if is_new:
                user.bot_conv_used = (user.bot_conv_used or 0) + 1
            usage = usage_snapshot(user)
            alert = _alert_due(user, usage)
            if alert:
                user.bot_conv_alert = alert
            await db.commit()
            if alert and user.email:
                _send_alert(user.email, user.business_name or "Tu negocio", usage, alert)
            return usage
    except Exception:
        logger.exception("[PLAN-USAGE] conversation count failed advertiser=%s", advertiser_id)
        return ConversationUsage(used=0, cap=-1, economy=False)


def _alert_due(user, usage: ConversationUsage) -> int:
    if usage.cap <= 0:
        return 0
    pct = usage.used * 100 // usage.cap
    due = max((lvl for lvl in ALERT_LEVELS if pct >= lvl), default=0)
    return due if due > (user.bot_conv_alert or 0) else 0


def _send_alert(email: str, business_name: str, usage: ConversationUsage, level: int) -> None:
    from app.core.email import send_plan_usage_email

    try:
        asyncio.get_running_loop().create_task(
            send_plan_usage_email(email, business_name, usage.used, usage.cap, level)
        )
    except RuntimeError:
        logger.warning("[PLAN-USAGE] no event loop to send %s%% alert", level)
