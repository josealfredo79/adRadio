"""Real-DB regression test for a production incident found 2026-08-13: a
second (or later) message from a contact with an existing, non-empty
Conversation crashed process_inbound_message with sqlalchemy.exc.
MissingGreenlet inside the just-added time-gap-note code, because it read
conv.last_activity AFTER it had already been reassigned to func.now() (and,
separately, after other work in the request could have expired the ORM
attribute). The webhook still returned 200 OK to Meta, so nothing retried —
the inbound message was silently dropped with zero reply and zero DB record.
Mocked-db tests (test_stop_word_optout.py etc.) never caught this because a
MagicMock conv never actually exercises SQLAlchemy's lazy-load path — this
needs a real Conversation object from a real session."""
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

PHONE = "+525511119999"


async def _seed_returning_contact():
    """A contact with an existing Conversation that already has messages —
    exactly the state that crashed in production (a brand-new conversation,
    with conv.messages == [], never hit this bug)."""
    await engine.dispose()
    await close_redis()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Negocio Test")
        db.add(user)
        await db.flush()
        contact = Contact(advertiser_id=user.id, name="Cliente Viejo", phone=PHONE, source="landing")
        db.add(contact)
        await db.flush()
        conv = Conversation(
            advertiser_id=user.id,
            contact_id=contact.id,
            messages=[
                {"role": "user", "content": "Hola, hace tiempo"},
                {"role": "assistant", "content": "¡Hola! ¿En qué te ayudo?"},
            ],
        )
        db.add(conv)
        await db.commit()
        return user.id, contact.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Message).where(Message.advertiser_id.in_(user_ids)))
        await db.execute(delete(Conversation).where(Conversation.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


class TestReturningContactDoesNotCrash:
    @pytest.mark.asyncio
    async def test_second_message_reaches_the_bot_without_crashing(self):
        user_id, contact_id = await _seed_returning_contact()
        try:
            with patch(
                "app.services.inbound_pipeline.answer_with_rag",
                new_callable=AsyncMock,
            ) as mock_rag:
                mock_rag.return_value = "¡Qué gusto verte de nuevo! 😊"
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    send = AsyncMock(return_value=("wamid.x", None))
                    msg = InboundMessage(advertiser=user, from_number=PHONE, body_text="Hola de nuevo")
                    result = await process_inbound_message(db, msg, send=send, send_owner=send)

            assert result == {"message": "ok"}
            mock_rag.assert_awaited_once()
            send.assert_awaited_once()

            async with AsyncSessionLocal() as db:
                conv = (
                    await db.execute(select(Conversation).where(Conversation.contact_id == contact_id))
                ).scalar_one()
                assert conv.messages[-1] == {"role": "assistant", "content": "¡Qué gusto verte de nuevo! 😊"}
        finally:
            await _cleanup([user_id])
