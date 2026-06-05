from pydantic import BaseModel, field_validator
import re


class ProfileUpdate(BaseModel):
    business_name: str | None = None
    business_category: str | None = None
    city: str | None = None
    country: str | None = None
    phone: str | None = None
    whatsapp_number: str | None = None
    language: str | None = None
    bot_name: str | None = None
    bot_personality: str | None = None
    bot_instructions: str | None = None
    widget_color: str | None = None
    widget_greeting: str | None = None
    widget_position: str | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not re.match(r"^\+\d{7,15}$", v):
            raise ValueError("El teléfono debe estar en formato E.164 (ej: +521234567890)")
        return v

    @field_validator("whatsapp_number")
    @classmethod
    def validate_whatsapp(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        # Accept with or without +
        clean = v.replace("+", "")
        if not clean.isdigit() or len(clean) < 7 or len(clean) > 15:
            raise ValueError("El WhatsApp debe tener entre 7 y 15 dígitos")
        # Add + if not present
        return f"+{clean}" if not v.startswith("+") else v

    @field_validator("bot_instructions")
    @classmethod
    def validate_bot_instructions(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if len(v) > 2000:
            raise ValueError("Las instrucciones no pueden exceder 2000 caracteres")
        return v

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str | None) -> str | None:
        if v and v not in ("es", "en", "pt"):
            raise ValueError("Idioma no soportado")
        return v


class DashboardResponse(BaseModel):
    contacts_total: int
    campaigns_active: int
    messages_sent_this_month: int
    messages_remaining: int
    plan: str | None
    subscription_status: str
