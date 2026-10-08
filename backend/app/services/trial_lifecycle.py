"""Fin de la prueba gratis: +5 días si el negocio la está usando; si no, pausa.

Prueba de 15 días (TRIAL_DAYS). Al vencer, si hubo indicios de uso en los
últimos 7 días (clientes que escribieron o agendaron, pedidos, el dueño
entró a su panel) se alarga TRIAL_EXTENSION_DAYS una sola vez. Si no, la
cuenta queda en pausa hasta que pague:

- su página muestra solo lo básico ("pronto volvemos a atender en línea"),
- su bot no usa IA: contesta un mensaje fijo (costo cero),
- no salen campañas.

Nada se borra: al pagar vuelve todo igual. Las cuentas con
`billing_exempt` (la de IaRadio, demos, admins) nunca se pausan.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = logging.getLogger(__name__)

TRIAL_EXTENSION_DAYS = 5
ACTIVITY_WINDOW = timedelta(days=7)
# La extensión se decide al vencer; si el worker estuvo caído, hay margen.
REVIEW_WINDOW = timedelta(days=2)
# Una cuenta que pagó y dejó de pagar queda así (Stripe / cleanup_expired_data).
INACTIVE_STATUSES = ("churned", "suspended")


def is_paused(user: User, now: datetime | None = None) -> bool:
    if user.billing_exempt:
        return False
    if user.subscription_status in INACTIVE_STATUSES:
        return True
    if user.subscription_status == "trial" and user.plan_expires_at is not None:
        return user.plan_expires_at < (now or datetime.now(timezone.utc))
    return False


def paused_reply(user: User) -> str:
    """Lo que contesta el bot de un negocio en pausa (sin IA)."""
    name = user.business_name or "el negocio"
    # Solo el número público del negocio; `phone` es el WhatsApp personal del dueño.
    phone = user.meta_display_phone_number if user.meta_connection_status == "connected" else ""
    contact = f" Puedes llamar al {phone}." if phone else ""
    return f"¡Gracias por escribir a {name}! 😊 Por ahora no estamos atendiendo en línea.{contact}"


def trial_days_left(user: User, now: datetime | None = None) -> int | None:
    """Días que le quedan a la prueba (None si no está en prueba o es exenta)."""
    if user.billing_exempt or user.subscription_status != "trial" or user.plan_expires_at is None:
        return None
    seconds = (user.plan_expires_at - (now or datetime.now(timezone.utc))).total_seconds()
    return max(0, int(-(-seconds // 86400)))


async def has_recent_activity(db: AsyncSession, user: User, now: datetime) -> bool:
    """¿El negocio usó su prueba en los últimos 7 días?"""
    from app.models.appointment import Appointment
    from app.models.message import Message
    from app.models.order import Order

    since = now - ACTIVITY_WINDOW
    if user.last_seen_at and user.last_seen_at >= since:
        return True
    for model, extra in (
        (Message, (Message.direction == "inbound",)),
        (Appointment, ()),
        (Order, ()),
    ):
        found = await db.execute(
            select(func.count()).select_from(model).where(
                model.advertiser_id == user.id, model.created_at >= since, *extra
            )
        )
        if found.scalar_one():
            return True
    return False


async def extend_active_trials(db: AsyncSession, now: datetime | None = None) -> int:
    """A las pruebas recién vencidas que se están usando les da 5 días más
    (una sola vez). Las demás se quedan vencidas = en pausa."""
    now = now or datetime.now(timezone.utc)
    expired = (await db.execute(
        select(User).where(
            User.subscription_status == "trial",
            User.billing_exempt.is_(False),
            User.trial_extended_at.is_(None),
            User.plan_expires_at.is_not(None),
            User.plan_expires_at < now,
            User.plan_expires_at >= now - REVIEW_WINDOW,
        )
    )).scalars().all()
    extended = 0
    for user in expired:
        if await has_recent_activity(db, user, now):
            user.plan_expires_at = now + timedelta(days=TRIAL_EXTENSION_DAYS)
            user.trial_extended_at = now
            extended += 1
            logger.info("[TRIAL] +%s días a %s (la está usando)", TRIAL_EXTENSION_DAYS, user.id)
    if extended:
        await db.commit()
    return extended
