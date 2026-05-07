import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    language: Mapped[str] = mapped_column(String(5), default="es")
    status: Mapped[str] = mapped_column(String(20), default="active")
    engagement_score: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    last_interaction: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    advertiser: Mapped["User"] = relationship(back_populates="contacts")  # noqa: F821
    messages: Mapped[list["Message"]] = relationship(back_populates="contact", cascade="all, delete-orphan")  # noqa: F821
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="contact", cascade="all, delete-orphan")  # noqa: F821

    __table_args__ = (
        CheckConstraint("status IN ('active','unsubscribed','blocked')", name="ck_contacts_status"),
        CheckConstraint("source IN ('manual','csv','landing','referral')", name="ck_contacts_source"),
        CheckConstraint("engagement_score BETWEEN 0 AND 100", name="ck_contacts_engagement"),
    )
