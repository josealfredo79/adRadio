import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="advertiser"
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verification_token: Mapped[str | None] = mapped_column(String(64))

    # Business info
    business_name: Mapped[str | None] = mapped_column(String(255))
    business_category: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(10), default="MX", server_default="MX")
    logo_url: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(20))
    whatsapp_number: Mapped[str | None] = mapped_column(String(20))
    # 'shared' = usa el número de AdRadio | 'pool' = asignado del pool | 'own' = WABA propio
    whatsapp_number_source: Mapped[str] = mapped_column(String(10), default="shared")

    # Subscription
    stripe_customer_id: Mapped[str | None] = mapped_column(String(50))
    subscription_status: Mapped[str] = mapped_column(
        String(20), default="trial", nullable=False
    )
    current_plan: Mapped[str] = mapped_column(String(20), default="trial")
    messages_remaining: Mapped[int] = mapped_column(Integer, default=0)
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Preferences
    language: Mapped[str] = mapped_column(String(5), default="es")
    bot_personality: Mapped[str] = mapped_column(String(50), default="professional", server_default="professional")
    bot_name: Mapped[str] = mapped_column(String(100), default="Asistente", server_default="Asistente")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    contacts: Mapped[list["Contact"]] = relationship(back_populates="advertiser", cascade="all, delete-orphan")
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="advertiser", cascade="all, delete-orphan")
    knowledge_base: Mapped[list["KnowledgeBase"]] = relationship(back_populates="advertiser", cascade="all, delete-orphan")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="advertiser", cascade="all, delete-orphan")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="advertiser", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'advertiser')", name="ck_users_role"),
        CheckConstraint(
            "subscription_status IN ('trial','active','suspended','churned')",
            name="ck_users_subscription_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
