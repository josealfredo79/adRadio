"""
Conversations router — /api/v1/conversations
Exposes the inbox of WhatsApp conversations for each advertiser.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all conversations for the current advertiser, newest activity first."""
    q = (
        select(Conversation, Contact)
        .outerjoin(Contact, Conversation.contact_id == Contact.id)
        .where(Conversation.advertiser_id == current_user.id)
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
            "message_count": len(conv.messages),
            "last_message": conv.messages[-1] if conv.messages else None,
            "contact": {
                "id": str(contact.id) if contact else None,
                "name": contact.name if contact else "Desconocido",
                "phone": contact.phone if contact else None,
                "engagement_score": contact.engagement_score if contact else 0,
            },
        }
        for conv, contact in rows
    ]


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually escalate or close a conversation."""
    new_status = body.get("status")
    if new_status not in ("active", "escalated", "closed"):
        raise HTTPException(status_code=400, detail="Estado inválido")

    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.advertiser_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    conv.status = new_status
    await db.commit()
    return {"message": f"Estado actualizado a {new_status}"}


@router.post("/{conversation_id}/reply")
async def reply_to_conversation(
    conversation_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a manual reply from the dashboard to a WhatsApp contact."""
    text = (body.get("text") or "").strip()
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

    return {"message": "ok", "msg_id": str(msg.id)}
