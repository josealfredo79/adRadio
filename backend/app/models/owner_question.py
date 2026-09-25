import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OwnerQuestion(Base):
    """Pregunta de un cliente que el bot no supo contestar y le reenvió al
    dueño por el número central de IaRadio ("Déjame preguntarle al dueño").

    `owner_wamid` es el id del mensaje que recibió el dueño: cuando responde
    citándolo, WhatsApp manda ese id en `context` y así sabemos a qué
    pregunta contesta aunque tenga varias abiertas."""

    __tablename__ = "owner_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    customer_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # pending → answered (o undeliverable si el cliente ya salió de la ventana de 24h)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    owner_wamid: Mapped[str | None] = mapped_column(String(100), index=True)
    answer: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
