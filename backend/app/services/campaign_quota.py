"""Cuántas campañas de audio (cuña) y de imagen (banner) puede mandar un
negocio al mes según su plan (spec docs/specs/2026-10-28-campanas-fase-a.md).

- Audio: el límite `radio` del plan (Negocio 4, Crecimiento 15, Empresa sin
  límite). El plan que no lo incluye (Arranque) tiene 1 de prueba al mes.
- Imagen: sin límite desde Negocio (`FEATURE_PLAN["banner"]`); antes, 1 de
  prueba al mes.

Se cuentan las campañas que salieron del borrador en los últimos 30 días, por
`ab_test.campaign_mode`. Antes se contaba por `Campaign.type`, que nunca es
"radio" (es promo/recordatorio/…), y el tope no frenaba a nadie.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import check_feature_access, get_radio_limit
from app.domain.campaign_actions import RADIO_MODES
from app.models.campaign import Campaign
from app.models.user import User

PERIOD_DAYS = 30
TRIAL_PER_MONTH = 1
# El tope empieza a contar el día que se subió (antes nunca frenó): las cuñas
# viejas no dejan sin cuñas este mes a nadie (revisor-dinero, 2026-10-28).
COUNT_FROM = datetime(2026, 10, 29, 6, tzinfo=timezone.utc)  # 00:00 en Tlaxiaco


def kind_of(mode: str | None) -> str | None:
    """"audio", "image" o None (texto y lo demás no tienen tope)."""
    if mode in RADIO_MODES:
        return "audio"
    if mode == "banner":
        return "image"
    return None


def monthly_limit(user: User, kind: str) -> tuple[int, bool]:
    """(límite, es_de_prueba); -1 = sin límite."""
    if kind == "audio":
        limit = get_radio_limit(user)
        return (TRIAL_PER_MONTH, True) if limit == 0 else (limit, False)
    if check_feature_access(user, "banner"):
        return -1, False
    return TRIAL_PER_MONTH, True


async def used_this_month(db: AsyncSession, user: User, kind: str, exclude=None) -> int:
    modes = RADIO_MODES if kind == "audio" else ("banner",)
    q = select(func.count()).select_from(Campaign).where(
        Campaign.advertiser_id == user.id,
        Campaign.status != "draft",
        Campaign.created_at >= max(COUNT_FROM, datetime.now(timezone.utc) - timedelta(days=PERIOD_DAYS)),
        Campaign.ab_test["campaign_mode"].astext.in_(modes),
        # La Parrilla Semanal se programa sola (campaign_ops.run_parrilla_generation):
        # no se come las cuñas que el dueño manda a mano.
        Campaign.name.not_like("Parrilla:%"),
    )
    if exclude is not None:
        q = q.where(Campaign.id != exclude)
    return (await db.execute(q)).scalar() or 0


def _blocked_text(kind: str, limit: int, trial: bool) -> str:
    if trial and kind == "audio":
        return "Tu audio de prueba de este mes ya lo usaste. El audio es del plan Negocio (4 al mes)."
    if trial:
        return "Tu imagen de prueba de este mes ya la usaste. Las imágenes son del plan Negocio."
    return (f"Ya usaste las {limit} cuñas de radio de tu plan este mes. "
            "Sube de plan para tener más (Negocio: 4, Crecimiento: 15).")


async def quota_block(db: AsyncSession, user: User, kind: str | None, exclude=None) -> str | None:
    """La frase de por qué no se puede, o None si todavía le quedan."""
    if kind is None:
        return None
    limit, trial = monthly_limit(user, kind)
    if limit < 0 or await used_this_month(db, user, kind, exclude=exclude) < limit:
        return None
    return _blocked_text(kind, limit, trial)


async def quota_summary(db: AsyncSession, user: User) -> dict:
    """Para la pantalla: {"audio": {limit, used, trial}, "image": {…}}."""
    out = {}
    for kind in ("audio", "image"):
        limit, trial = monthly_limit(user, kind)
        out[kind] = {"limit": limit, "used": await used_this_month(db, user, kind), "trial": trial}
    return out
