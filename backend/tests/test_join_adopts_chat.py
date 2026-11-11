"""El visitante anónimo que se registra con código desde el chat ("🔔 Avísame"
o el registro para pedir) se lleva lo que ya platicó en esa sesión: sin esto,
activaba avisos y el seguimiento nunca tenía qué recordarle
(spec 2026-11-10-avisame-y-segundo-recordatorio, caso 3)."""
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import redis.asyncio as aioredis
from sqlalchemy import delete, select

from app.api.v1.join import join_code, join_verify
from app.api.v1.widget import CHAT_REDIS_PREFIX
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.portal_service import read_portal_token
from app.services.web_conversation import ANON_CHAT_PREFIX
from tests.test_join import _cleanup, _request, _seed

TRANSCRIPT = [
    {"role": "assistant", "content": "¡Hola! ¿En qué te ayudo?"},
    {"role": "user", "content": "¿cuánto cuesta el cargador?"},
    {"role": "assistant", "content": "El cargador marca cuesta $120."},
]


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-for-join")
    monkeypatch.setattr(settings, "CUSTOMER_ACCOUNT_ENABLED", True)


def test_same_redis_key_as_the_widget():
    assert ANON_CHAT_PREFIX == CHAT_REDIS_PREFIX


async def _join_from_chat(slug, user_id, session_id, redis):
    send = AsyncMock(return_value=True)
    phone = f"55{uuid.uuid4().int % 10**8:08d}"
    with patch("app.api.v1.join.send_code", send):
        async with AsyncSessionLocal() as db:
            await join_code(request=_request(), slug=slug, body={"name": "Ana", "phone": phone}, db=db, redis=redis)
    body = {"name": "Ana", "phone": phone, "code": send.await_args.args[1]}
    if session_id:
        body["session_id"] = session_id
    async with AsyncSessionLocal() as db:
        out = await join_verify(request=_request(), slug=slug, body=body, db=db, redis=redis)
    return read_portal_token(out["portal_path"].removeprefix("/c/"))


async def _wipe(user_id):
    async with AsyncSessionLocal() as db:
        for model in (Message, Conversation):
            await db.execute(delete(model).where(model.advertiser_id == user_id))
        await db.commit()
    await _cleanup(user_id)


@pytest.mark.asyncio
async def test_anonymous_chat_moves_to_the_new_customer():
    user_id, slug = await _seed()
    redis = aioredis.from_url(settings.REDIS_URL)
    session = str(uuid.uuid4())
    try:
        await redis.setex(f"{CHAT_REDIS_PREFIX}{user_id}:{session}", 1800, json.dumps(TRANSCRIPT))
        cid = await _join_from_chat(slug, user_id, session, redis)
        async with AsyncSessionLocal() as db:
            conv = (await db.execute(select(Conversation).where(Conversation.contact_id == cid))).scalar_one()
            msgs = (await db.execute(select(Message).where(Message.contact_id == cid)
                                     .order_by(Message.created_at))).scalars().all()
        assert [t["content"] for t in conv.messages] == [t["content"] for t in TRANSCRIPT]
        assert all(t["channel"] == "web" for t in conv.messages)
        # "cuánto" = interesado: el seguimiento lo toma en cuenta.
        assert conv.lead_score == "hot"
        assert [(m.direction, m.channel) for m in msgs] == [("outbound", "web"), ("inbound", "web"), ("outbound", "web")]
        assert msgs[1].content == "¿cuánto cuesta el cargador?"
        # Se pasa una sola vez.
        assert await redis.get(f"{CHAT_REDIS_PREFIX}{user_id}:{session}") is None
    finally:
        await redis.aclose()
        await _wipe(user_id)


@pytest.mark.asyncio
async def test_without_session_or_transcript_nothing_moves():
    user_id, slug = await _seed()
    redis = aioredis.from_url(settings.REDIS_URL)
    try:
        for session in (None, str(uuid.uuid4())):
            cid = await _join_from_chat(slug, user_id, session, redis)
            async with AsyncSessionLocal() as db:
                assert (await db.execute(select(Message).where(Message.contact_id == cid))).first() is None
    finally:
        await redis.aclose()
        await _wipe(user_id)


@pytest.mark.asyncio
async def test_other_business_session_is_not_taken():
    """La llave lleva el negocio: una sesión de otro negocio no se cuela."""
    user_id, slug = await _seed()
    redis = aioredis.from_url(settings.REDIS_URL)
    session = str(uuid.uuid4())
    other = uuid.uuid4()
    try:
        await redis.setex(f"{CHAT_REDIS_PREFIX}{other}:{session}", 1800, json.dumps(TRANSCRIPT))
        cid = await _join_from_chat(slug, user_id, session, redis)
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(Message).where(Message.contact_id == cid))).first() is None
    finally:
        await redis.delete(f"{CHAT_REDIS_PREFIX}{other}:{session}")
        await redis.aclose()
        await _wipe(user_id)
