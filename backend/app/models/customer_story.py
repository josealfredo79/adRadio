import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CustomerStory(Base):
    __tablename__ = "customer_stories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    media_url: Mapped[str] = mapped_column(Text, nullable=False)
    transcription: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment: Mapped[str] = mapped_column(String(20), default="neutro")
    # 'pending' | 'approved' | 'rejected'. `approved` se mantiene en sync por
    # compatibilidad con lecturas viejas; el estado canónico es `status`.
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    # Consentimiento para publicar la voz + primer nombre del cliente. Mandar
    # la nota de voz ES el acto de consentimiento; guardamos el texto que se le
    # mostró en la invitación y cuándo.
    consent_text: Mapped[str | None] = mapped_column(Text)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    coupon_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("coupons.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    advertiser: Mapped["User"] = relationship(foreign_keys=[advertiser_id])  # noqa: F821
    contact: Mapped["Contact | None"] = relationship(foreign_keys=[contact_id])  # noqa: F821
    campaign: Mapped["Campaign | None"] = relationship(foreign_keys=[campaign_id])  # noqa: F821
    coupon: Mapped["Coupon | None"] = relationship(foreign_keys=[coupon_id])  # noqa: F821
