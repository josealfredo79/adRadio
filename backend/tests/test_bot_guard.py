"""Seguridad contra bots: campo trampa, tope global de códigos, contactos del
widget sin consentimiento confirmado y tope de chats anónimos por negocio."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.api.v1.join import join_code
from app.api.v1.widget import ANON_LIMIT_REPLY, widget_capture_lead, widget_chat
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.services import customer_account as ca
from tests.test_customer_account import MemRedis
from tests.test_join import _cleanup as _cleanup_join
from tests.test_join import _on, _request, _seed  # noqa: F401  (_on: fixture autouse)
from tests.test_widget_endpoints import _cleanup, _seed_user
from tests.test_widget_endpoints import _request as _wreq


@pytest.mark.asyncio
async def test_honeypot_on_join_pretends_success_and_sends_nothing():
    uid, slug = await _seed()
    try:
        send = AsyncMock(return_value=True)
        with patch("app.api.v1.join.send_code", send):
            async with AsyncSessionLocal() as db:
                out = await join_code(request=_request(), slug=slug,
                                      body={"name": "Bot", "phone": "5511112222", "website": "http://spam.example"},
                                      db=db, redis=MemRedis())
        assert "código" in out["message"]
        send.assert_not_awaited()
    finally:
        await _cleanup_join(uid)


@pytest.mark.asyncio
async def test_global_daily_code_cap(monkeypatch):
    monkeypatch.setattr(settings, "OTP_GLOBAL_DAILY_MAX", 3)
    redis = MemRedis()
    for i in range(3):
        await ca.issue_code(redis, f"52551111000{i}")
    with pytest.raises(ca.CodeError) as e:
        await ca.issue_code(redis, "525511110009")
    assert "Por ahora no podemos" in str(e.value)


@pytest.mark.asyncio
async def test_widget_lead_is_unconfirmed_and_honeypot_creates_nothing():
    uid = await _seed_user()
    try:
        async with AsyncSessionLocal() as db:
            out = await widget_capture_lead(request=_wreq(method="POST"), advertiser_id=uid,
                                            body={"name": "Luis", "phone": "+525511117777"}, db=db, redis=None)
        async with AsyncSessionLocal() as db:
            contact = await db.get(Contact, uuid.UUID(out["contact_id"]))
            assert contact.consent_status == "unconfirmed"
        async with AsyncSessionLocal() as db:
            await widget_capture_lead(request=_wreq(method="POST"), advertiser_id=uid,
                                      body={"name": "Bot", "phone": "+525599998888", "website": "x"}, db=db, redis=None)
        async with AsyncSessionLocal() as db:
            n = (await db.execute(select(Contact).where(Contact.advertiser_id == uid))).scalars().all()
            assert len(n) == 1
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Conversation).where(Conversation.advertiser_id == uid))
            await db.execute(delete(Contact).where(Contact.advertiser_id == uid))
            await db.commit()
        await _cleanup([uid])


@pytest.mark.asyncio
async def test_anonymous_chats_have_a_daily_cap_per_business(monkeypatch):
    from tests.test_portal_web_shift import FakeRedis

    monkeypatch.setattr(settings, "WEB_ANON_CHATS_DAILY_MAX", 2)
    uid = await _seed_user(business_name="Tacos")
    redis = FakeRedis()
    try:
        rag = AsyncMock(return_value="¡Hola! Abrimos a las 9.")
        with patch("app.services.rag_service.answer_with_rag", rag):
            replies = []
            for _ in range(3):
                async with AsyncSessionLocal() as db:
                    out = await widget_chat(request=_wreq(method="POST"), advertiser_id=uid,
                                            body={"message": "¿a qué hora abren?"}, db=db, redis=redis)
                replies.append(out["reply"])
        assert replies[:2] == ["¡Hola! Abrimos a las 9."] * 2
        assert replies[2] == ANON_LIMIT_REPLY
        assert rag.await_count == 2  # el tercero no llamó a la IA
    finally:
        await _cleanup([uid])
