"""
Conversations router — /api/v1/conversations
Exposes the inbox of WhatsApp conversations for each advertiser.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from redis.asyncio import Redis as AsyncRedis
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.api.deps import get_current_user
from app.api.idempotency import idempotent_post, store_idempotency_response
from app.core.redis import get_redis_optional
from app.database import get_db
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


class StatusUpdateBody(BaseModel):
    status: Literal["active", "closed"]


class LeadScoreUpdateBody(BaseModel):
    lead_score: Literal["hot", "warm", "cold"] | None = None


class ReplyBody(BaseModel):
    text: str


@router.get("")
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all conversations for the current advertiser, newest activity first."""
    msg_count = (
        select(Message.contact_id, func.count(Message.id).label("cnt"))
        .where(Message.advertiser_id == current_user.id)
        .group_by(Message.contact_id)
        .subquery()
    )

    latest_msg = (
        select(
            Message.contact_id,
            Message.content,
            Message.direction,
            func.row_number().over(
                partition_by=Message.contact_id,
                order_by=Message.created_at.desc(),
            ).label("rn"),
        )
        .where(Message.advertiser_id == current_user.id)
        .subquery()
    )

    q = (
        select(
            Conversation,
            Contact,
            func.coalesce(msg_count.c.cnt, 0).label("message_count"),
            latest_msg.c.content,
            latest_msg.c.direction,
        )
        .outerjoin(Contact, Conversation.contact_id == Contact.id)
        .outerjoin(msg_count, Conversation.contact_id == msg_count.c.contact_id)
        .outerjoin(
            latest_msg,
            (Conversation.contact_id == latest_msg.c.contact_id)
            & (latest_msg.c.rn == 1),
        )
        .where(Conversation.advertiser_id == current_user.id)
        .options(defer(Conversation.messages))
    )
    if status_filter:
        q = q.where(Conversation.status == status_filter)

    q = q.order_by(desc(Conversation.last_activity)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    rows = result.all()

    return [
        {
            "id": str(conv.id),
            "status": conv.status,
            "lead_score": conv.lead_score,
            "tags": conv.tags,
            "last_activity": conv.last_activity,
            "message_count": message_count,
            "last_message": {"role": "assistant" if direction == "outbound" else "user", "content": content}
            if content else None,
            "contact": {
                "id": str(contact.id) if contact else None,
                "name": contact.name if contact else "Desconocido",
                "phone": contact.phone if contact else None,
                "engagement_score": contact.engagement_score if contact else 0,
            },
        }
        for conv, contact, message_count, content, direction in rows
    ]


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return full conversation history for a single conversation."""
    result = await db.execute(
        select(Conversation, Contact)
        .outerjoin(Contact, Conversation.contact_id == Contact.id)
        .where(
            Conversation.id == conversation_id,
            Conversation.advertiser_id == current_user.id,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    conv, contact = row
    return {
        "id": str(conv.id),
        "status": conv.status,
        "lead_score": conv.lead_score,
        "tags": conv.tags,
        "last_activity": conv.last_activity,
        "messages": conv.messages,
        "contact": {
            "id": str(contact.id) if contact else None,
            "name": contact.name if contact else "Desconocido",
            "phone": contact.phone if contact else None,
            "engagement_score": contact.engagement_score if contact else 0,
        },
    }


@router.patch("/{conversation_id}/status")
async def update_conversation_status(
    conversation_id: uuid.UUID,
    body: StatusUpdateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Manually escalate or close a conversation."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.advertiser_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    conv.status = body.status
    await db.commit()
    return {"message": f"Estado actualizado a {body.status}"}


@router.patch("/{conversation_id}/lead-score")
async def update_lead_score(
    conversation_id: uuid.UUID,
    body: LeadScoreUpdateBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Manually set lead score: hot, warm, cold, or null to clear."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.advertiser_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    conv.lead_score = body.lead_score
    await db.commit()
    return {"message": f"Lead score actualizado a {body.lead_score}"}


@router.post("/{conversation_id}/reply")
async def reply_to_conversation(
    conversation_id: uuid.UUID,
    request: Request,
    body: ReplyBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(idempotent_post),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict[str, str]:
    """Send a manual reply from the dashboard to a WhatsApp contact."""
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Mensaje vacío")
    if len(text) > 4096:
        raise HTTPException(status_code=400, detail="Mensaje demasiado largo")

    # Load conversation + contact
    result = await db.execute(
        select(Conversation, Contact)
        .outerjoin(Contact, Conversation.contact_id == Contact.id)
        .where(
            Conversation.id == conversation_id,
            Conversation.advertiser_id == current_user.id,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    conv, contact = row
    if not contact or not contact.phone:
        raise HTTPException(status_code=400, detail="Contacto sin número de teléfono")

    # Save outbound message record
    msg = Message(
        advertiser_id=current_user.id,
        contact_id=contact.id,
        direction="outbound",
        content=text,
        status="queued",
    )
    db.add(msg)

    # Append to conversation messages array
    messages = list(conv.messages or [])
    messages.append({"role": "assistant", "content": text})
    conv.messages = messages
    conv.last_activity = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(msg)

    # Queue Twilio send via Celery
    from app.workers.tasks import send_whatsapp_message
    send_whatsapp_message.apply_async(
        args=[str(msg.id), contact.phone, text],
        countdown=1,
    )

    out = {"message": "ok", "msg_id": str(msg.id)}
    await store_idempotency_response(request, redis, out)
    return out
