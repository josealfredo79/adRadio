from pydantic import BaseModel, field_validator


class MetaWhatsappCredentials(BaseModel):
    waba_id: str
    phone_number_id: str
    token: str

    @field_validator("waba_id", "phone_number_id", "token")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Este campo no puede estar vacío")
        return v


class MetaWhatsappTestResult(BaseModel):
    ok: bool
    display_phone_number: str | None = None
    verified_name: str | None = None
    code: str | None = None
    message: str | None = None


class MetaWhatsappConnectionOut(BaseModel):
    waba_id: str | None = None
    phone_number_id: str | None = None
    display_phone_number: str | None = None
    verified_name: str | None = None
    status: str
    token_last4: str | None = None
    utility_template_status: str
    utility_template_name: str | None = None
    appointment_template_name: str | None = None


class MetaWhatsappHealthOut(BaseModel):
    """Capa 15 anti-baneo: snapshot de salud de la cuenta para que el
    advertiser vea de un vistazo el estado de todo lo que las capas 6-14
    vienen aplicando en segundo plano — sin esto, un auto-pause por rating
    RED o por un error de riesgo de baneo (capa 13) es invisible hasta que
    el advertiser nota que sus campañas dejaron de enviarse."""
    quality_rating: str | None = None
    messaging_tier: str | None = None
    tier_recipient_limit: int | None = None
    send_throttle_per_hour: int
    connected_at: str | None = None
    warmup_active: bool
    warmup_recipient_cap: int | None = None
    warmup_days_remaining: float | None = None
    recipients_sent_last_24h: int
    effective_recipient_limit: int | None = None
    active_campaigns_count: int
    paused_campaigns_count: int
