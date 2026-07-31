"""
Reacts to WhatsApp number quality signals from Meta — shared by the
real-time webhook (meta_incoming.py, field `phone_number_quality_update`,
which only ever carries FLAGGED/UNFLAGGED) and the Celery Beat poll of the
Graph API (tasks.poll_meta_quality_ratings), which is the only source for
the real GREEN/YELLOW/RED rating.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.campaign import Campaign

logger = logging.getLogger(__name__)

_BASELINE_PER_HOUR = 60
_THROTTLED_PER_HOUR = _BASELINE_PER_HOUR // 2

# Meta's documented messaging_limit_tier values — caps unique customers the
# business can start a NEW 24h conversation window with, per rolling 24h
# period. Includes both the current vocabulary and the older TIER_50/TIER_1K
# values this repo's own webhook fixtures reference, since some accounts may
# still report them. Re-verify against a live Graph API response if Meta
# renames this scheme again (they've flagged messaging_limit_tier as being
# superseded by whatsapp_business_manager_messaging_limit).
_TIER_LIMITS: dict[str, int | None] = {
    "TIER_50": 50,
    "TIER_250": 250,
    "TIER_1K": 1_000,
    "TIER_2K": 2_000,
    "TIER_10K": 10_000,
    "TIER_100K": 100_000,
    "TIER_UNLIMITED": None,  # None = sin tope
}
# Fallback usado cuando meta_messaging_tier es None (aún no se ha hecho el
# primer poll) o un string no reconocido (Meta cambió el vocabulario) —
# fail-open pero conservador: ni bloquea todo el envío (fail-closed
# rompería el onboarding) ni deja sin tope (fail-open-ilimitado anularía
# el propósito de esta capa). Se autocorrige en el siguiente poll de 30 min.
_DEFAULT_TIER_LIMIT = 250


def resolve_tier_limit(tier: str | None) -> int | None:
    """Resuelve el string crudo de messaging_limit_tier a un tope numérico
    de destinatarios únicos por ventana móvil de 24h. Devuelve None solo
    para un tier reconocido como ilimitado."""
    if tier is None:
        return _DEFAULT_TIER_LIMIT
    if tier not in _TIER_LIMITS:
        logger.warning(
            "[TIER] messaging_limit_tier desconocido=%r — usando tope conservador=%d",
            tier, _DEFAULT_TIER_LIMIT,
        )
        return _DEFAULT_TIER_LIMIT
    return _TIER_LIMITS[tier]


# Capa 11 — rampa de warm-up para números recién conectados a Meta. Meta
# banea/limita agresivamente números que arrancan enviando a tope de tier
# desde el día 1 (patrón típico de spam); esta rampa reduce el tope de
# destinatarios únicos/24h por debajo del que ya impone messaging_limit_tier
# mientras el número es nuevo, sin importar qué tier reporte Meta todavía
# (un número nuevo normalmente ni siquiera tiene tier asignado aún).
# (días desde la conexión, tope) — ordenado ascendente, primer umbral que
# cubre a `días_conectado` gana.
_WARMUP_RAMP: list[tuple[int, int]] = [
    (2, 20),
    (6, 50),
    (13, 150),
    (29, 500),
]


def resolve_warmup_cap(connected_at: datetime | None) -> int | None:
    """Tope de warm-up vigente según cuántos días lleva conectado el número,
    o None si ya completó la rampa. `connected_at=None` también devuelve
    None (sin restricción) — números conectados antes de que existiera esta
    columna se tratan como ya calentados, no se restringen retroactivamente."""
    if connected_at is None:
        return None
    days_connected = (datetime.now(timezone.utc) - connected_at).total_seconds() / 86400
    for days_threshold, cap in _WARMUP_RAMP:
        if days_connected <= days_threshold:
            return cap
    return None


# Capa 13 — códigos de error de Meta que señalan riesgo real de baneo a
# nivel de CUENTA (no solo "reintenta este mensaje"), suficiente para
# pausar toda campaña activa del advertiser, igual que un rating RED
# (ver apply_quality_signal arriba). Meta formatea sus mensajes de error
# como "(#<code>) <descripción>"; 131049 es lo bastante largo para
# matchear tal cual, 368 se busca con la forma "(#368)" para no
# confundirse con un "368" suelto en otro contexto del mensaje.
# Fuente: referencia oficial de códigos de error de WhatsApp Cloud API
# (developers.facebook.com/.../whatsapp/support/error-codes).
# 131049 = "This message was not delivered to maintain healthy ecosystem
#           engagement" — Meta mismo empieza a frenar la entrega por baja
#           interacción predicha, un antecedente directo de una caída de
#           quality rating.
# 368     = "Temporarily blocked for policies violations" — bloqueo de
#           Meta a nivel de cuenta, no una falla de un solo mensaje.
_BAN_RISK_ERROR_CODES = ("131049", "(#368)")


def is_ban_risk_error(error: str | None) -> bool:
    """True si un error de envío de WhatsApp señala riesgo de baneo/
    restricción a nivel de cuenta por parte de Meta, a diferencia de una
    falla de entrega ordinaria de un solo mensaje."""
    if not error:
        return False
    return any(code in error for code in _BAN_RISK_ERROR_CODES)


async def pause_active_campaigns(db, advertiser_id) -> None:
    result = await db.execute(
        select(Campaign).where(
            Campaign.advertiser_id == advertiser_id,
            Campaign.status.in_(("scheduled", "running")),
        )
    )
    campaigns = result.scalars().all()
    for campaign in campaigns:
        campaign.status = "paused"
    if campaigns:
        logger.warning(
            "[META QUALITY] Auto-paused %d campaign(s) for advertiser=%s — number flagged by Meta",
            len(campaigns), advertiser_id,
        )


async def apply_quality_signal(db, advertiser, rating: str | None, tier: str | None = None) -> None:
    """Update the advertiser's known rating/tier and react to it: RED pauses
    every active campaign, YELLOW halves the hourly send cap, GREEN restores
    the baseline cap. Any other value (e.g. Meta's "NA" for a brand-new
    number) is just recorded, no reaction."""
    if rating:
        advertiser.meta_quality_rating = rating
    if tier:
        advertiser.meta_messaging_tier = tier

    if rating == "YELLOW":
        advertiser.meta_send_throttle_per_hour = _THROTTLED_PER_HOUR
    elif rating == "GREEN":
        advertiser.meta_send_throttle_per_hour = _BASELINE_PER_HOUR

    if rating == "RED":
        await pause_active_campaigns(db, advertiser.id)

    await db.commit()
