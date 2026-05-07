import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProspectsPool(Base):
    __tablename__ = "prospects_pool"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(255))
    interests: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    city: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(10))
    language: Mapped[str] = mapped_column(String(5), default="es")
    opt_in_source: Mapped[str | None] = mapped_column(String(255))
    opt_in_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    opt_in_proof_url: Mapped[str] = mapped_column(Text, nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    last_contact: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
