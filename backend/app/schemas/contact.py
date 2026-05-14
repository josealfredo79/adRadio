import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator
import re


def validate_phone_e164(v: str) -> str:
    if not re.match(r"^\+\d{7,15}$", v):
        raise ValueError("El teléfono debe estar en formato E.164 (ej: +521234567890)")
    return v


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


class ContactUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    city: str | None = None
    tags: list[str] | None = None
    language: str | None = None
    notes: str | None = None
    status: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in ("active", "unsubscribed"):
            raise ValueError("Solo puedes cambiar a active o unsubscribed")
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
    engagement_score: int
    source: str
    last_interaction: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ContactListResponse(BaseModel):
    items: list[ContactOut]
    total: int
    page: int
    page_size: int
