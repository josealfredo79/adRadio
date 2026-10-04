"""Una sola plática por cliente, sea por WhatsApp o por el chat web del
portal (/c/{token}).

- Lo que se platica en la web también queda en Conversation.messages, así el
  dueño lo ve en el Inbox y el bot recuerda lo que se dijo por el otro canal.
- Si el dueño pausó el bot (conversación "escalated"), el bot tampoco
  contesta en la web: el mensaje le llega al dueño, igual que en WhatsApp.
- Lo que el dueño contesta desde el Inbox le llega por la web (aviso push,
  gratis) a quien la usa; WhatsApp (cobrado por Meta) queda de respaldo.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message

logger = logging.getLogger(__name__)

MAX_CONV_MESSAGES = 40  # mismo recorte que inbound_pipeline.py
# El cliente escribió en el chat web hace menos de esto: sigue ahí (el chat
# del portal revisa si hay respuestas nuevas mientras está abierto).
WEB_ACTIVE_WINDOW = timedelta(minutes=30)


async def open_conversation(db: AsyncSession, advertiser_id: uuid.UUID, contact_id: uuid.UUID) -> Conversation:
    """La plática abierta del cliente (activa o con el bot pausado), o una nueva."""
    conv = (
        await db.execute(
            select(Conversation)
            .where(
                Conversation.advertiser_id == advertiser_id,
                Conversation.contact_id == contact_id,
                Conversation.status.in_(("active", "escalated")),
            )
            .order_by(Conversation.last_activity.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if conv is None:
        conv = Conversation(advertiser_id=advertiser_id, contact_id=contact_id, messages=[], lead_score="cold")
        db.add(conv)
        await db.flush()
    return conv


def log_turns(conv: Conversation, *turns: dict) -> None:
    """Agrega turnos ({"role", "content", ...}) a la plática. Se reasigna la
    lista completa: JSONB no detecta cambios hechos en el lugar."""
    conv.messages = (list(conv.messages or []) + list(turns))[-MAX_CONV_MESSAGES:]
    conv.last_activity = datetime.now(timezone.utc)


async def recently_on_web(db: AsyncSession, contact_id: uuid.UUID) -> bool:
    since = datetime.now(timezone.utc) - WEB_ACTIVE_WINDOW
    found = (
        await db.execute(
            select(Message.id).where(
                Message.contact_id == contact_id,
                Message.direction == "inbound",
                Message.channel == "web",
                Message.created_at > since,
            ).limit(1)
        )
    ).first()
    return found is not None


async def push_owner_reply(db: AsyncSession, business_name: str, contact_id: uuid.UUID, text: str) -> int:
    """Aviso web con la respuesta del dueño; al tocarlo se abre el chat del
    portal con la respuesta. Regresa cuántos navegadores lo aceptaron."""
    from app.services.portal_service import portal_url
    from app.services.web_push import push_to_contact

    try:
        return await push_to_contact(
            db, contact_id,
            title=f"{business_name or 'El negocio'} te respondió",
            body=text,
            url=f"{portal_url(contact_id)}?chat=1",
            tag=f"reply-{contact_id}",
        )
    except Exception:
        logger.warning("[WEB-CONV] owner reply push failed contact=%s", contact_id, exc_info=True)
        return 0
