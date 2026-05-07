import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(20))
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    qr_code_url: Mapped[str | None] = mapped_column(Text)
    segment: Mapped[dict] = mapped_column(JSONB, default=dict)
    schedule: Mapped[dict] = mapped_column(JSONB, default=dict)
    ab_test: Mapped[dict] = mapped_column(JSONB, default=lambda: {"enabled": False})
    status: Mapped[str] = mapped_column(String(20), default="draft")
    stats: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: {
            "sent": 0,
            "delivered": 0,
            "read": 0,
            "replied": 0,
            "failed": 0,
            "coupons_redeemed": 0,
        },
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    advertiser: Mapped["User"] = relationship(back_populates="campaigns")  # noqa: F821
    messages: Mapped[list["Message"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")  # noqa: F821

    __table_args__ = (
        CheckConstraint(
            "type IN ('promo','reminder','launch','event')", name="ck_campaigns_type"
        ),
        CheckConstraint(
            "status IN ('draft','scheduled','running','paused','completed')",
            name="ck_campaigns_status",
        ),
    )
