import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    # URL slug for the AdRadio-hosted public landing page (/sitio/{slug}) —
    # optional, null until the advertiser claims one.
    slug: Mapped[str | None] = mapped_column(String(60), unique=True)
    # Short welcome line shown on that landing page, written via the
    # landing-page setup wizard — separate from widget_greeting (chat opener).
    landing_tagline: Mapped[str | None] = mapped_column(String(140))
    # Weekly schedule for self-service appointment booking, e.g.
    # {"mon": ["09:00","18:00"], ..., "sun": null}. Null/missing day = closed.
    # Falls back to availability_service.DEFAULT_BUSINESS_HOURS when unset.
    business_hours: Mapped[dict | None] = mapped_column(JSONB)
    country: Mapped[str] = mapped_column(String(10), default="MX", server_default="MX")
    logo_url: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(20))
    # Número personal del dueño del negocio para notificaciones (pedido nuevo,
    # cita agendada, etc.) — independiente del número de WhatsApp Business
    # conectado vía Meta (ver meta_display_phone_number más abajo).
    whatsapp_number: Mapped[str | None] = mapped_column(String(20))

    # WhatsApp Cloud API de Meta — conexión directa
    meta_waba_id: Mapped[str | None] = mapped_column(String(50))
    meta_phone_number_id: Mapped[str | None] = mapped_column(String(50))
    meta_display_phone_number: Mapped[str | None] = mapped_column(String(20))
    meta_verified_name: Mapped[str | None] = mapped_column(String(255))
    meta_token_cipher: Mapped[str | None] = mapped_column(Text)
    meta_token_iv: Mapped[str | None] = mapped_column(String(64))
    meta_token_tag: Mapped[str | None] = mapped_column(String(64))
    # 'not_connected' | 'connected' | 'reconnect_required'
    meta_connection_status: Mapped[str] = mapped_column(String(20), default="not_connected", server_default="not_connected")
    # Cuándo se conectó el número de WhatsApp actual (meta_phone_number_id).
    # Solo se reinicia si cambia el número — reconectar el mismo número (ej.
    # refrescar el token) no reinicia la rampa de warm-up (ver Capa 11 en
    # meta_quality_service.py).
    meta_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 'not_configured' | 'pending_review' | 'approved' | 'rejected'
    meta_utility_template_status: Mapped[str] = mapped_column(String(20), default="not_configured", server_default="not_configured")
    meta_utility_template_name: Mapped[str | None] = mapped_column(String(255))
    meta_appointment_template_name: Mapped[str | None] = mapped_column(String(255))
    # meta_quality_rating/meta_messaging_tier: se actualizan tanto por el
    # webhook (phone_number_quality_update, solo FLAGGED/UNFLAGGED) como por
    # el polling periódico al Graph API (trae el rating real GREEN/YELLOW/RED).
    meta_quality_rating: Mapped[str | None] = mapped_column(String(10))
    meta_messaging_tier: Mapped[str | None] = mapped_column(String(20))
    # Cap de envíos/hora efectivo — 60 normalmente, se reduce a la mitad
    # automáticamente si el rating cae a YELLOW (ver meta_quality_service.py).
    meta_send_throttle_per_hour: Mapped[int] = mapped_column(Integer, default=60, server_default="60")

    # Subscription
    stripe_customer_id: Mapped[str | None] = mapped_column(String(50))
    subscription_status: Mapped[str] = mapped_column(
        String(20), default="trial", nullable=False
    )
    current_plan: Mapped[str] = mapped_column(String(20), default="trial")
    messages_remaining: Mapped[int] = mapped_column(Integer, default=50)
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Preferences
    language: Mapped[str] = mapped_column(String(5), default="es")
    bot_personality: Mapped[str] = mapped_column(String(50), default="professional", server_default="professional")
    bot_name: Mapped[str] = mapped_column(String(100), default="Asistente", server_default="Asistente")
    bot_instructions: Mapped[str | None] = mapped_column(Text)

    # Google Calendar OAuth
    google_refresh_token: Mapped[str | None] = mapped_column(Text)
    google_calendar_connected: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Widget customization
    widget_color: Mapped[str] = mapped_column(String(7), default="#25D366", server_default="#25D366")
    widget_greeting: Mapped[str] = mapped_column(String(200), default="¡Hola! ¿En qué puedo ayudarte?", server_default="¡Hola! ¿En qué puedo ayudarte?")
    widget_position: Mapped[str] = mapped_column(String(10), default="right", server_default="right")

    # White-label settings
    white_label: Mapped[dict] = mapped_column(JSONB, default=dict)

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
