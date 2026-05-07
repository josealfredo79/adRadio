import uuid
from datetime import datetime
from pydantic import BaseModel


class KnowledgeBaseOut(BaseModel):
    id: uuid.UUID
    filename: str
    file_type: str
    version: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TestBotRequest(BaseModel):
    question: str


class TestBotResponse(BaseModel):
    answer: str
    sources_found: int
