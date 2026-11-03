"""BAJA por el chat web hace lo mismo que por WhatsApp: el cliente deja de recibir
promos y lo que esperaba su respuesta ya no sale. Base real; la IA es falsa."""
import uuid

import pytest
from sqlalchemy import select

from app.api.v1.widget import UNVERIFIED_SESSION_PREFIX, widget_chat
from app.database import AsyncSessionLocal
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.inbound_pipeline import UNSUBSCRIBED_REPLY
from tests.test_web_conversation import (  # noqa: F401 — fixture autouse
    _cleanup,
    _request,
    _secret,
    _seed,
)
from tests.test_web_conversation import _web_chat as _chat


async def _pending(user_id, cid):
    async with AsyncSessionLocal() as db:
        db.add(Message(advertiser_id=user_id, contact_id=cid, direction="outbound",
                       content="[PENDING:text] 2x1 en micas", status="queued"))
        await db.commit()


async def _state(cid):
    async with AsyncSessionLocal() as db:
        contact = await db.get(Contact, cid)
        pending = (await db.execute(
            select(Message.status).where(Message.contact_id == cid, Message.content.like("[PENDING:%"))
        )).scalar_one()
        return contact.status, pending


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["BAJA", "baja.", "Stop"])
async def test_baja_on_the_web_unsubscribes_and_cancels_what_was_waiting(text):
    user_id, cid, _ = await _seed()
    try:
        await _pending(user_id, cid)
        out, rag = await _chat(user_id, cid, text)
        assert out["reply"] == UNSUBSCRIBED_REPLY
        rag.assert_not_called()
        assert await _state(cid) == ("unsubscribed", "failed")
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_baja_works_even_while_the_owner_is_attending():
    user_id, cid, _ = await _seed(status="escalated")
    try:
        await _pending(user_id, cid)
        out, _ = await _chat(user_id, cid, "baja")
        assert out["reply"] == UNSUBSCRIBED_REPLY
        assert await _state(cid) == ("unsubscribed", "failed")
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["no quiero", "salir", "quiero darme de baja de la cita"])
async def test_answers_inside_the_chat_do_not_unsubscribe(text):
    user_id, cid, _ = await _seed()
    try:
        await _pending(user_id, cid)
        out, _ = await _chat(user_id, cid, text)
        assert out["reply"] != UNSUBSCRIBED_REPLY
        assert await _state(cid) == ("active", "queued")
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_an_unverified_visitor_cannot_unsubscribe_a_number():
    """Tecleó un teléfono en el chat: no prueba que sea suyo."""
    from app.api.v1.widget import SESSION_CONTACT_REDIS_PREFIX
    from tests.test_portal_web_shift import FakeRedis

    user_id, cid, _ = await _seed()
    try:
        redis = FakeRedis()
        session = str(uuid.uuid4())
        await redis.setex(f"{SESSION_CONTACT_REDIS_PREFIX}{user_id}:{session}", 60, str(cid))
        await redis.setex(f"{UNVERIFIED_SESSION_PREFIX}{user_id}:{session}", 60, "1")
        from unittest.mock import AsyncMock, patch
        with patch("app.services.rag_service.answer_with_rag", AsyncMock(return_value="¿En qué te ayudo?")), \
                patch("app.services.realtime.publish_conversation_event", AsyncMock()):
            async with AsyncSessionLocal() as db:
                out = await widget_chat(request=_request(), advertiser_id=user_id,
                                        body={"message": "BAJA", "session_id": session}, db=db, redis=redis)
        assert out["reply"] != UNSUBSCRIBED_REPLY
        async with AsyncSessionLocal() as db:
            assert (await db.get(Contact, cid)).status == "active"
            assert (await db.execute(select(Conversation).where(Conversation.contact_id == cid))).scalar_one()
    finally:
        await _cleanup(user_id)
