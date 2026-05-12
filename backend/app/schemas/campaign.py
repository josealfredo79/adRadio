import uuid
from datetime import datetime

from pydantic import BaseModel


class CampaignCreate(BaseModel):
    name: str
    type: str
    message_text: str
    image_url: str | None = None
    segment: dict = {}
    schedule: dict = {}
    ab_test: dict = {"enabled": False}
    status: str = "draft"


class CampaignUpdate(BaseModel):
    name: str | None = None
    message_text: str | None = None
    image_url: str | None = None
    segment: dict | None = None
    schedule: dict | None = None
    status: str | None = None


class CampaignOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    message_text: str
    image_url: str | None
    qr_code_url: str | None
    segment: dict
    schedule: dict
    ab_test: dict
    status: str
    stats: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class GenerateContentRequest(BaseModel):
    campaign_type: str
    business_name: str
    intent: str  # descripción en lenguaje natural


class GenerateContentResponse(BaseModel):
    variants: list[str]  # 3 variantes del mensaje


class GenerateImageRequest(BaseModel):
    campaign_name: str
    message_text: str
    business_name: str


class GenerateSequenceRequest(BaseModel):
    business_name: str
    intent: str
    campaign_type: str = "promo"


class GenerateSagaRequest(BaseModel):
    business_name: str
    product_description: str
    protagonist_name: str = "María"


class GenerateSequenceResponse(BaseModel):
    messages: list[str]  # 3 msgs para sequence, 4 para saga


class GenerateRadioAdRequest(BaseModel):
    business_name: str
    intent: str
    country: str = "mx"  # mx | co | ar | es
    mode: str = "classic"  # "classic" | "comunitaria" | "capsula" | "trivia" | "historia" | "alerta" | "estacional"
    business_category: str | None = None  # inmobiliaria, restaurante, tienda, etc.
    extra_context: str | None = None  # premio de trivia, fecha/temporada, dato extra


class ParrillaRequest(BaseModel):
    business_name: str
    intent: str          # propósito/mensaje central de la semana
    country: str = "mx"
    business_category: str | None = None
    extra_context: str | None = None   # contexto extra (temporada, promo activa, etc.)
    # Si True, programa el envío automático a los contactos activos
    auto_schedule: bool = False
    # Hora local preferida de envío (formato "HH:MM"), default 10:00
    send_time: str = "10:00"


class ParrillaDayOut(BaseModel):
    day: int          # 0=Lun … 6=Dom
    day_name: str
    mode: str
    mode_emoji: str
    script: str
    audio_url: str | None = None  # None si la generación de audio falló


class ParrillaOut(BaseModel):
    days: list[ParrillaDayOut]
    plan: str          # plan del usuario que generó esto
    auto_scheduled: bool

