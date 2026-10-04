import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LoyaltyStamp(Base):
    """Un sello en la tarjeta de lealtad de un cliente (ver loyalty_service.py).
    Una fila por sello: lo que dio el sello (`source` + `source_key`, ej.
    "appointment" + id de la cita) es único, así una cita o un pedido nunca
    sella dos veces aunque el dueño le pique dos veces o el bot reintente.

    Al entregar el premio, los sellos usados se marcan `redeemed_at` — la
    tarjeta "actual" son los que no lo tienen."""

    __tablename__ = "loyalty_stamps"
    __table_args__ = (UniqueConstraint("contact_id", "source", "source_key", name="uq_loyalty_stamp_source"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # welcome | push | appointment | order | manual
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_key: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
