from datetime import datetime

from pydantic import BaseModel


class LabFindingOut(BaseModel):
    type: str
    severity: str
    evidence: str
    suggestion: str


class LabConversationOut(BaseModel):
    id: str
    persona_key: str
    persona_label: str
    transcript: list[dict]
    score: int | None
    findings: list[LabFindingOut]


class LabRunOut(BaseModel):
    id: str
    status: str
    overall_score: int | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class LabRunDetailOut(LabRunOut):
    conversations: list[LabConversationOut]


class LabRunStarted(BaseModel):
    id: str
    status: str
