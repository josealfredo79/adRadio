import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CampaignSegmentSend(Base):
    """Tracks when a given segment/list (not an individual contact) was last
    blasted, per advertiser — closes the gap where the per-contact 48h
    cooldown (Contact.last_campaign_sent_at) doesn't stop the *same list*
    from being relaunched wholesale every couple of days."""

    __tablename__ = "campaign_segment_sends"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # sha256 of the canonicalized segment definition (sorted tags or sorted
    # specific_contacts ids) — identifies "the same list" across campaigns.
    segment_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("advertiser_id", "segment_fingerprint", name="uq_campaign_segment_sends_advertiser_fingerprint"),
    )
