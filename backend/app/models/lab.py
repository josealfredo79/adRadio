import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LabRun(Base):
    """One run of the Laboratorio — all 6 personas against the real bot."""
    __tablename__ = "lab_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="running", server_default="running")
    overall_score: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    conversations: Mapped[list["LabConversation"]] = relationship(
        back_populates="lab_run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("status IN ('running','completed','error')", name="ck_lab_runs_status"),
        CheckConstraint("overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)", name="ck_lab_runs_score_range"),
    )


class LabConversation(Base):
    """One simulated persona's conversation + judge evaluation within a LabRun."""
    __tablename__ = "lab_conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lab_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lab_runs.id", ondelete="CASCADE"), nullable=False
    )
    persona_key: Mapped[str] = mapped_column(String(50), nullable=False)
    persona_label: Mapped[str] = mapped_column(String(100), nullable=False)
    transcript: Mapped[list] = mapped_column(JSONB, default=list)
    score: Mapped[int | None] = mapped_column(Integer)
    findings: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lab_run: Mapped["LabRun"] = relationship(back_populates="conversations")

    __table_args__ = (
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_lab_conversations_score_range"),
    )
