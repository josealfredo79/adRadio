from pydantic import BaseModel, EmailStr


class ProfileUpdate(BaseModel):
    business_name: str | None = None
    city: str | None = None
    country: str | None = None
    language: str | None = None
    bot_name: str | None = None
    bot_personality: str | None = None


class DashboardResponse(BaseModel):
    contacts_total: int
    campaigns_active: int
    messages_sent_this_month: int
    messages_remaining: int
    plan: str | None
    subscription_status: str
