"""
Appointment schemas — request/response models for the appointments API.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel


class AppointmentCreate(BaseModel):
    customer_name: str
    customer_phone: str | None = None
    service: str
    scheduled_at: datetime
    duration_min: int = 30
    notes: str | None = None
    contact_id: uuid.UUID | None = None


class AppointmentUpdate(BaseModel):
    customer_name: str | None = None
    customer_phone: str | None = None
    service: str | None = None
    scheduled_at: datetime | None = None
    duration_min: int | None = None
    notes: str | None = None
    status: str | None = None  # confirmed | cancelled | completed | no_show


class AppointmentOut(BaseModel):
    id: uuid.UUID
    customer_name: str
    customer_phone: str | None
    service: str
    scheduled_at: datetime
    duration_min: int
    notes: str | None
    status: str
    google_event_id: str | None
    contact_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
