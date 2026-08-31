"""Turn the silent anti-ban/compliance gates into something the advertiser
can actually read.

Two entry points:

* ``preflight_campaign_send`` — run BEFORE flipping a campaign to running
  (the resume endpoint). If the send would be blocked wholesale the instant
  it dispatched, return a human sentence so the caller can 400 instead of
  showing a false "campaign resumed" and letting it silently re-pause.

* ``explain_campaign_pause`` — given a campaign that is already paused,
  look up the most recent send_block_logs row and describe why, plus when
  it can run again. Surfaced on the campaign card.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.campaign_segment_send import CampaignSegmentSend
from app.models.send_block_log import SendBlockLog
from app.models.user import User
from app.workers.task_helpers.campaign_ops import (
    _SEGMENT_RELAUNCH_COOLDOWN_DAYS,
    get_recipient_cap_state,
    segment_fingerprint,
)

_MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _fecha(dt: datetime) -> str:
    """'7 de septiembre' — sin año salvo que no sea el año en curso."""
    hoy = datetime.now(timezone.utc)
    base = f"{dt.day} de {_MESES[dt.month - 1]}"
    return base if dt.year == hoy.year else f"{base} de {dt.year}"


def _human(reason: str, *, retry_after: datetime | None = None, detail: str | None = None) -> str:
    """Copy escrita para el dueño de un negocio, no para un técnico: qué
    pasó en palabras de todos los días + qué hacer ahora."""
    cuando = f" Podrás enviarla el {_fecha(retry_after)}." if retry_after else ""
    return {
        "segment_cooldown": (
            "Le escribiste a estas personas hace muy poco. Enviar tan seguido "
            "puede hacer que WhatsApp bloquee tu número." + cuando
        ),
        "recipient_cap": (
            "Por hoy alcanzaste el límite de contactos nuevos de WhatsApp. "
            "Inténtalo mañana."
        ),
        "no_messages_remaining": (
            "Se acabaron los mensajes de tu plan. Renueva o espera a que se "
            "reinicie tu cuota."
        ),
        "high_failure_rate": (
            "Muchos mensajes no llegaron (números mal escritos o sin WhatsApp). "
            "Revisa tu lista de contactos."
        ),
        "consent_unconfirmed": (
            "Estas personas aún no confirmaron que quieren tus promociones. "
            "Falta que respondan “Sí” a tu mensaje de permiso."
        ),
        "no_utility_template": (
            "Pasaron más de 24 horas desde su último mensaje. Para escribirles "
            "necesitas una plantilla aprobada."
        ),
    }.get(reason, "La campaña está en pausa por una regla de WhatsApp.")


async def _segment_cooldown_until(db: AsyncSession, advertiser_id, segment: dict) -> datetime | None:
    fp = segment_fingerprint(segment or {})
    row = (
        await db.execute(
            select(CampaignSegmentSend).where(
                CampaignSegmentSend.advertiser_id == advertiser_id,
                CampaignSegmentSend.segment_fingerprint == fp,
            )
        )
    ).scalar_one_or_none()
    if not row:
        return None
    until = row.last_sent_at + timedelta(days=_SEGMENT_RELAUNCH_COOLDOWN_DAYS)
    return until if until > datetime.now(timezone.utc) else None


async def preflight_campaign_send(
    db: AsyncSession, campaign: Campaign, advertiser: User,
) -> str | None:
    """Return a human sentence if dispatching this campaign right now would
    be blocked wholesale, else None."""
    if advertiser.messages_remaining is not None and advertiser.messages_remaining <= 0:
        return _human("no_messages_remaining")

    until = await _segment_cooldown_until(db, campaign.advertiser_id, campaign.segment or {})
    if until:
        return _human("segment_cooldown", retry_after=until)

    cap = await get_recipient_cap_state(db, advertiser)
    if cap.limit is not None and cap.count >= cap.limit:
        return _human("recipient_cap", detail=f"{cap.count}/{cap.limit}")

    return None


async def explain_campaign_pause(db: AsyncSession, campaign: Campaign) -> dict | None:
    """Describe why an already-paused campaign is paused, from its most
    recent send_block_logs row. Returns None if there is no logged reason
    (e.g. the advertiser paused it by hand)."""
    if campaign.status != "paused":
        return None

    log = (
        await db.execute(
            select(SendBlockLog)
            .where(SendBlockLog.campaign_id == campaign.id)
            .order_by(SendBlockLog.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not log:
        return None

    retry_after = None
    if log.reason == "segment_cooldown":
        retry_after = await _segment_cooldown_until(
            db, campaign.advertiser_id, campaign.segment or {}
        )

    return {
        "reason": log.reason,
        "message": _human(log.reason, retry_after=retry_after, detail=log.detail),
        "retry_after": retry_after.isoformat() if retry_after else None,
        "blocked_at": log.created_at.isoformat() if log.created_at else None,
    }
