import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL")
    )
    messages: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")
    lead_score: Mapped[str | None] = mapped_column(String(10))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    advertiser: Mapped["User"] = relationship(back_populates="conversations")  # noqa: F821
    contact: Mapped["Contact | None"] = relationship(back_populates="conversations")  # noqa: F821

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','escalated','closed')", name="ck_conv_status"
        ),
        CheckConstraint(
            "lead_score IN ('hot','warm','cold')", name="ck_conv_lead_score"
        ),
    )
