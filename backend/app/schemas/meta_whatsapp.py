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
