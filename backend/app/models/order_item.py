import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OrderItem(Base):
    """Best-effort link between an Order's free-text items_raw and a real
    Product, matched at order-creation time (see catalog_service.py's
    match_products_in_text). Purely additive analytics — never changes what
    the advertiser sees/fulfills, which always reads items_raw directly."""

    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), index=True
    )

    product_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    order: Mapped["Order"] = relationship(foreign_keys=[order_id])  # noqa: F821
    product: Mapped["Product | None"] = relationship(foreign_keys=[product_id])  # noqa: F821
