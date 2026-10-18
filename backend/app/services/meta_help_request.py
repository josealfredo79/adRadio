"""Un dueño pide ayuda para conectar su WhatsApp (docs/specs/2026-10-17-meta-sin-friccion.md).

Mientras "Conectar con Meta" siga solo para admins, el dueño toca "Quiero
conectar mi WhatsApp" y la petición queda como plática en el Inbox de la
cuenta del número central de IaRadio, con el bot pausado para que el bot de
ventas no le conteste. No se manda nada por WhatsApp: no cuesta.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.contact import Contact
from app.models.message import Message
from app.models.user import User
from app.services.customer_account import canonical_phone, contact_phone_canonical
from app.services.web_conversation import log_turns, open_conversation

logger = logging.getLogger(__name__)

HELP_TAG = "quiere_whatsapp"
# Tocar el botón otra vez dentro de este tiempo no agrega otro mensaje.
REPEAT_WINDOW = timedelta(hours=24)


async def central_account(db: AsyncSession) -> User | None:
    if not settings.IARADIO_WA_PHONE_NUMBER_ID:
        return None
    return (
        await db.execute(
            select(User).where(User.meta_phone_number_id == settings.IARADIO_WA_PHONE_NUMBER_ID).limit(1)
        )
    ).scalar_one_or_none()


def _help_text(owner: User) -> str:
    who = owner.business_name or owner.email
    return f"Quiero conectar mi WhatsApp (pedido desde el panel). Negocio: {who} · cuenta {owner.email}"


async def request_whatsapp_help(db: AsyncSession, owner: User) -> bool:
    """Guarda la petición en el Inbox de IaRadio. False si no hay cuenta del
    número central o el dueño no tiene teléfono al cual contactarlo."""
    central = await central_account(db)
    phone = canonical_phone(owner.phone or owner.whatsapp_number)
    if central is None or phone is None or central.id == owner.id:
        return False

    contact = (
        await db.execute(
            select(Contact)
            .where(Contact.advertiser_id == central.id, contact_phone_canonical() == phone)
            .limit(1)
        )
    ).scalar_one_or_none()
    if contact is None:
        contact = Contact(advertiser_id=central.id, name=owner.business_name or "Dueño", phone=f"+{phone}")
        db.add(contact)
        await db.flush()

    conv = await open_conversation(db, central.id, contact.id)
    conv.status = "escalated"  # el bot de ventas no le contesta: lo atiende una persona
    if HELP_TAG not in (conv.tags or []):
        conv.tags = list(conv.tags or []) + [HELP_TAG]

    since = datetime.now(timezone.utc) - REPEAT_WINDOW
    text = _help_text(owner)
    already = (
        await db.execute(
            select(Message.id).where(
                Message.advertiser_id == central.id,
                Message.contact_id == contact.id,
                Message.direction == "inbound",
                Message.content == text,
                Message.created_at > since,
            ).limit(1)
        )
    ).first()
    if already is None:
        db.add(Message(
            advertiser_id=central.id, contact_id=contact.id, direction="inbound",
            content=text, status="delivered", channel="web",
        ))
        log_turns(conv, {"role": "user", "content": text})
    await db.commit()
    logger.info("[META HELP] %s asked for help connecting WhatsApp", owner.id)
    return True
