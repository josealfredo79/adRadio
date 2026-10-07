"""El contacto toma el nombre de perfil de WhatsApp que manda Meta, en vez de
quedar con su teléfono como nombre. Un nombre que el dueño ya puso no se toca."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.core.redis import close_redis
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.services.inbound_pipeline import InboundMessage, process_inbound_message

PHONE = "+525511117777"


async def _seed(contact_name: str | None):
    await engine.dispose()
    await close_redis()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Negocio Test")
        db.add(user)
        await db.flush()
        if contact_name is not None:
            db.add(Contact(advertiser_id=user.id, name=contact_name, phone=PHONE, source="landing"))
        await db.commit()
        return user.id


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Message).where(Message.advertiser_id == user_id))
        await db.execute(delete(Conversation).where(Conversation.advertiser_id == user_id))
        await db.execute(delete(Contact).where(Contact.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def _receive(user_id, profile_name):
    with patch("app.services.inbound_pipeline.answer_with_rag", new_callable=AsyncMock) as mock_rag:
        mock_rag.return_value = "¡Hola!"
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            send = AsyncMock(return_value=("wamid.x", None))
            msg = InboundMessage(advertiser=user, from_number=PHONE, body_text="Hola, ¿qué precios tienen?",
                                 profile_name=profile_name)
            await process_inbound_message(db, msg, send=send, send_owner=send)
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(Contact.name).where(Contact.advertiser_id == user_id))).scalar_one()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "existing, profile, expected",
    [
        (None, "María López", "María López"),  # contacto nuevo
        (None, None, PHONE),  # Meta no mandó nombre
        (PHONE, "María López", "María López"),  # se había creado con el teléfono
        ("Mary (la de la tienda)", "María López", "Mary (la de la tienda)"),  # el dueño ya le puso nombre
    ],
)
async def test_contact_name_comes_from_whatsapp_profile(existing, profile, expected):
    user_id = await _seed(existing)
    try:
        assert await _receive(user_id, profile) == expected
    finally:
        await _cleanup(user_id)
