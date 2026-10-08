import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


def validate_phone_e164(v: str) -> str:
    """Acepta el número como lo escribe la gente ("953 123 4567", "+52 953-123-4567",
    "9531234567") y lo guarda como +52XXXXXXXXXX. Antes solo pasaba el formato
    exacto +52… y todo lo demás era un 422 sin explicación."""
    from app.services.customer_account import canonical_phone

    digits = canonical_phone(v)
    if digits is None:
        raise ValueError("Escribe el WhatsApp a 10 dígitos, por ejemplo 953 123 4567")
    return f"+{digits}"


class ContactCreate(BaseModel):
    name: str
    phone: str
    email: str | None = None
    city: str | None = None
    tags: list[str] = []
    language: str = "es"
    notes: str | None = None

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v: str) -> str:
        return validate_phone_e164(v)


PIPELINE_STAGES = ("nuevo", "conversacion", "interesado", "cliente", "perdido")


class ContactUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    city: str | None = None
    tags: list[str] | None = None
    language: str | None = None
    notes: str | None = None
    status: str | None = None
    engagement_score: int | None = None
    pipeline_stage: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in ("active", "unsubscribed"):
            raise ValueError("Solo puedes cambiar a active o unsubscribed")
        return v

    @field_validator("pipeline_stage")
    @classmethod
    def validate_pipeline_stage(cls, v: str | None) -> str | None:
        if v is not None and v not in PIPELINE_STAGES:
            raise ValueError(f"Etapa inválida — debe ser una de: {', '.join(PIPELINE_STAGES)}")
        return v


class ContactOut(BaseModel):
    id: uuid.UUID
    name: str
    phone: str
    email: str | None
    city: str | None
    tags: list[str]
    language: str
    status: str
    consent_status: str
    engagement_score: int
    source: str
    pipeline_stage: str
    last_interaction: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ContactListResponse(BaseModel):
    items: list[ContactOut]
    total: int
    page: int
    page_size: int
