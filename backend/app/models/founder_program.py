import uuid
from datetime import datetime

from sqlalchemy import Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class FounderProgram(Base):
    """Single-row counter for the 'Fundadores' launch program — a fixed
    number of Starter/Growth slots at a locked-in discounted price for the
    first customers. slots_used is only ever incremented via an atomic
    `UPDATE ... WHERE slots_used < slots_total` to avoid overselling under
    concurrent checkouts (see claim_founder_slot in payments.py)."""

    __tablename__ = "founder_program"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slots_total: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    slots_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
