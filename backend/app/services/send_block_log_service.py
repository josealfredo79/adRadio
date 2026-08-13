"""One place to record why a send got silently blocked by an anti-ban/
compliance gate — see app.models.send_block_log for the reason codes and the
motivation (built 2026-08-13 after repeatedly having to grep server logs
across 4+ separate gates to answer "why didn't this send")."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.send_block_log import SendBlockLog


def log_send_block(
    db: AsyncSession,
    advertiser_id: uuid.UUID,
    reason: str,
    *,
    campaign_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    detail: str | None = None,
) -> None:
    """Queues the log row on the given session — does NOT commit. Call
    alongside whatever commit the caller was already about to do, so a
    logging failure can never be the reason a block/pause doesn't persist."""
    db.add(SendBlockLog(
        advertiser_id=advertiser_id,
        campaign_id=campaign_id,
        contact_id=contact_id,
        reason=reason,
        detail=detail,
    ))
