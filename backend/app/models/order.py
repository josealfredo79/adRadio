import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )

    # Sequential display number per advertiser (set on creation)
    order_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # State machine:
    # collecting_name → collecting_address → collecting_payment → confirmed | cancelled
    state: Mapped[str] = mapped_column(String(30), default="collecting_name", nullable=False)

    # Order data collected step by step
    items_raw: Mapped[str | None] = mapped_column(Text)        # "2 pizzas de pepperoni"
    customer_name: Mapped[str | None] = mapped_column(String(200))
    delivery_address: Mapped[str | None] = mapped_column(Text)
    payment_method: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)

    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    advertiser: Mapped["User"] = relationship(foreign_keys=[advertiser_id])  # noqa: F821
    contact: Mapped["Contact | None"] = relationship(foreign_keys=[contact_id])  # noqa: F821
