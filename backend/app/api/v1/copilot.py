"""
Copiloto CRM router — /api/v1/copilot

Chat interno del dashboard: el anunciante autenticado opera su propio CRM
(contactos, campañas, cupones, citas) en lenguaje natural, respaldado por
tool-calling de Claude (ver app/services/copilot_service.py). Nunca toca
WhatsApp/Meta — es una capa de conversación sobre la propia API REST de la
app.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limiter import limiter
from app.core.redis import get_redis_optional
from app.database import get_db
from app.models.user import User
from app.services.copilot_service import handle_chat, handle_confirm, handle_tool_preview

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/copilot", tags=["copilot"])

# El cliente puede acumular un historial largo — solo mandamos las últimas
# MAX_HISTORY vueltas a Claude (recorte silencioso, no error).
MAX_HISTORY = 20


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ActionOut(BaseModel):
    tool: str
    summary: str
    data: dict = {}


class PendingConfirmationOut(BaseModel):
    confirmation_id: str
    tool: str
    summary: str
    args: dict


class CopilotResponse(BaseModel):
    reply: str
    actions: list[ActionOut] = []
    pending_confirmation: PendingConfirmationOut | None = None


class ConfirmRequest(BaseModel):
    confirmation_id: str
    approve: bool


class ToolPreviewRequest(BaseModel):
    args: dict = {}


@router.post("/chat", response_model=CopilotResponse)
@limiter.limit("20/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CopilotResponse:
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=422, detail="El mensaje no puede estar vacío")

    history = [h.model_dump() for h in body.history[-MAX_HISTORY:]]
    result = await handle_chat(db, current_user, body.message.strip(), history)
    return CopilotResponse(**result)


@router.post("/confirm", response_model=CopilotResponse)
@limiter.limit("20/minute")
async def confirm(
    request: Request,
    body: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> CopilotResponse:
    try:
        result = await handle_confirm(db, current_user, body.confirmation_id, body.approve, redis=redis)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CopilotResponse(**result)


@router.post("/tools/{tool_name}/preview", response_model=CopilotResponse)
@limiter.limit("20/minute")
async def tool_preview(
    tool_name: str,
    request: Request,
    body: ToolPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CopilotResponse:
    """Entrada de las mini-app cards (formulario real, no texto libre) — arma
    la confirmación directo desde `body.args`, sin pasar por Claude."""
    try:
        result = await handle_tool_preview(db, current_user, tool_name, body.args)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CopilotResponse(**result)
