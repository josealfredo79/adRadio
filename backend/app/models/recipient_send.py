import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RecipientSend(Base):
    """Layer 10 (messaging_limit_tier enforcement): una fila por cada
    ventana de conversación NUEVA abierta por el negocio hacia un contacto,
    por advertiser. Append-only — se usa para contar destinatarios únicos
    distintos tocados en las últimas 24h y hacer cumplir el
    messaging_limit_tier oficial de Meta. NO se escribe en cada mensaje —
    solo cuando _ensure_conversation_window realmente abre/reabre una
    ventana (re-mensajear una ventana ya abierta no cuenta)."""

    __tablename__ = "recipient_sends"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
