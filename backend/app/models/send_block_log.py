import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Reason codes — one per anti-ban/compliance gate that can silently block a
# send. Kept as plain strings (not a DB enum) so a new gate never needs a
# migration to add its code.
REASON_SEGMENT_COOLDOWN = "segment_cooldown"  # Capa 9: same contact list relaunched within 7 days
REASON_CONTACT_COOLDOWN = "contact_cooldown"  # 48h since this contact's last campaign
REASON_CONTACT_SUPPRESSED = "contact_suppressed"  # repeated send failures
REASON_CONTACT_INACTIVE = "contact_inactive"  # opted out / low engagement / stale
REASON_RECIPIENT_CAP = "recipient_cap"  # Capa 10/11: messaging_limit_tier or warm-up cap reached
REASON_NO_MESSAGES_REMAINING = "no_messages_remaining"  # plan quota exhausted
REASON_HIGH_FAILURE_RATE = "high_failure_rate"  # campaign auto-paused mid-send
REASON_CONSENT_UNCONFIRMED = "consent_unconfirmed"  # cold bulk-imported contact, no verified opt-in
REASON_NO_UTILITY_TEMPLATE = "no_utility_template"  # closed window, no approved template configured


class SendBlockLog(Base):
    """Audit trail of every send an anti-ban/compliance gate silently
    blocked — the single place that answers "why didn't this get sent",
    instead of grepping server logs across 4+ separate gates scattered
    through campaign_ops.py/tasks.py. Purely additive/read-side; nothing
    reads this to make sending decisions."""

    __tablename__ = "send_block_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    advertiser: Mapped["User"] = relationship(foreign_keys=[advertiser_id])  # noqa: F821
    campaign: Mapped["Campaign | None"] = relationship(foreign_keys=[campaign_id])  # noqa: F821
    contact: Mapped["Contact | None"] = relationship(foreign_keys=[contact_id])  # noqa: F821
