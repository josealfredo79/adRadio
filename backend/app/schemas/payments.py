import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class PlanInfo(BaseModel):
    name: str
    price: float
    messages: int
    days: int


class CheckoutRequest(BaseModel):
    plan: str  # starter | growth | pro | business | enterprise


class CheckoutResponse(BaseModel):
    checkout_url: str


class TransactionOut(BaseModel):
    id: uuid.UUID
    amount: Decimal
    currency: str
    plan: str | None
    status: str
    invoice_pdf_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
