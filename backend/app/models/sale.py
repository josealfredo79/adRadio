import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Sale(Base):
    """Lo que el negocio cobró (ver sales_service.py): un cobro de mostrador
    ("Cobré $85") o un pedido confirmado con monto. Es lo que deja medir si
    IaRadio le trae dinero al negocio. `contact_id` vacío = venta sin cliente.

    Un pedido da una sola venta (`source` + `source_key` únicos por negocio)."""

    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_sales_amount_positive"),
        CheckConstraint("source IN ('counter','order')", name="ck_sales_source"),
        Index("uq_sales_order", "advertiser_id", "source", "source_key", unique=True,
              postgresql_where="source = 'order'"),
        Index("ix_sales_advertiser_created", "advertiser_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # counter | order
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="counter")
    source_key: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
