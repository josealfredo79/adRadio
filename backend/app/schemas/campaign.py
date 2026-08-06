import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class CampaignCreate(BaseModel):
    name: str
    type: str
    message_text: str
    image_url: str | None = None
    segment: dict = {}
    schedule: dict = {}
    ab_test: dict = {"enabled": False}
    status: str = "draft"

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"promo", "reminder", "launch", "event", "voces"}
        if v not in allowed:
            raise ValueError(f"Tipo inválido: {v}. Debe ser uno de {', '.join(sorted(allowed))}")
        return v


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
    message_counts: dict = {}
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
    business_category: str | None = None


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
    voice_id: str | None = None  # edge-tts voice ID override (ej: es-MX-DaliaNeural)
    include_sfx: bool = False  # efectos de sonido opcionales (ding/whoosh/coin según modo)


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
    # Preferencias de banner (opcional)
    banner_palette: str | None = None   # paleta de colores (promo, verde, oscuro, etc.)
    banner_layout: str | None = None    # diseño (clasico, centrado, split, minimal)


class ParrillaDayOut(BaseModel):
    day: int          # 0=Lun … 6=Dom
    day_name: str
    mode: str
    mode_emoji: str
    format: str = "audio"  # "audio" | "banner"
    script: str
    audio_url: str | None = None  # None si la generación de audio falló
    banner_url: str | None = None  # URL del banner si format="banner"


class ParrillaJobOut(BaseModel):
    job_id: str


class ParrillaStatusOut(BaseModel):
    status: str  # "pending" | "running" | "done" | "error"
    total_days: int
    current_day: int  # días completados hasta ahora
    days: list[ParrillaDayOut] = []  # se va llenando conforme cada día termina
    plan: str
    auto_scheduled: bool
    error: str | None = None


class CustomerStoryOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID | None
    contact_name: str | None = None
    media_url: str
    transcription: str
    sentiment: str
    approved: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomerStoryListOut(BaseModel):
    stories: list[CustomerStoryOut]
    total: int
    approved_count: int
    pending_count: int

