"""Una sola plática por cliente, WhatsApp + web (web_conversation.py) —
real-DB: por dónde sale la respuesta del dueño, el bot pausado también en la
web, y el historial unido que ve el cliente en su portal."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import delete, select
from starlette.requests import Request

from app.api.v1.conversations import ReplyBody, reply_to_conversation
from app.api.v1.portal import get_messages
from app.api.v1.widget import SESSION_CONTACT_REDIS_PREFIX, widget_chat
from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services.portal_service import make_portal_token
from tests.test_portal_web_shift import FakeRedis


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-for-web-conv")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://www.iaradio.online")
    # Avisos web "configurados"; el envío real se reemplaza en cada test.
    monkeypatch.setattr("app.services.web_push.push_enabled", lambda: True)


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/x", "headers": [],
                    "client": (f"test-{uuid.uuid4()}", 1), "query_string": b""})


async def _seed(status="active", push=False, web_minutes_ago=None):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Barbería Don Pepe")
        db.add(user)
        await db.flush()
        contact = Contact(advertiser_id=user.id, name="Ana", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        db.add(contact)
        await db.flush()
        conv = Conversation(advertiser_id=user.id, contact_id=contact.id, status=status,
                            messages=[{"role": "user", "content": "hola por WhatsApp"}])
        db.add(conv)
        if push:
            db.add(PushSubscription(advertiser_id=user.id, contact_id=contact.id, p256dh="k", auth="a",
                                    endpoint=f"https://fcm.googleapis.com/fcm/send/{uuid.uuid4()}"))
        if web_minutes_ago is not None:
            db.add(Message(advertiser_id=user.id, contact_id=contact.id, direction="inbound", content="¿y el precio?",
                           status="delivered", channel="web",
                           created_at=datetime.now(timezone.utc) - timedelta(minutes=web_minutes_ago)))
        await db.commit()
        return user.id, contact.id, conv.id


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for model in (PushSubscription, Message, Campaign, Conversation, Contact):
            await db.execute(delete(model).where(model.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


async def _reply(user_id, conv_id, text="Sí lo tenemos 👍", channel="auto", accepted=1):
    push = AsyncMock(return_value=accepted)
    task = MagicMock()
    with patch("app.services.web_push.push_to_contact", push), \
            patch("app.workers.tasks.send_whatsapp_message", task), \
            patch("app.services.realtime.publish_conversation_event", AsyncMock()):
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            out = await reply_to_conversation(conv_id, request=_request(), body=ReplyBody(text=text, channel=channel),
                                              db=db, current_user=user, _=None, redis=None)
    return out, push, task


class TestOwnerReplyChannel:
    @pytest.mark.asyncio
    async def test_customer_with_notifications_gets_it_by_web_not_whatsapp(self):
        user_id, cid, conv_id = await _seed(push=True)
        try:
            out, push, task = await _reply(user_id, conv_id)
            assert out["channel"] == "web"
            task.apply_async.assert_not_called()
            kw = push.await_args.kwargs
            assert kw["title"] == "Barbería Don Pepe te respondió" and kw["body"] == "Sí lo tenemos 👍"
            assert kw["url"].endswith(f"/c/{make_portal_token(cid)}?chat=1")
            async with AsyncSessionLocal() as db:
                msg = (await db.execute(select(Message).where(Message.contact_id == cid, Message.sender == "owner"))).scalar_one()
                assert (msg.channel, msg.status) == ("web", "sent")
                conv = await db.get(Conversation, conv_id)
                assert conv.messages[-1] == {"role": "assistant", "content": "Sí lo tenemos 👍", "sender": "owner", "channel": "web"}
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_customer_without_web_gets_whatsapp(self):
        user_id, cid, conv_id = await _seed()
        try:
            out, push, task = await _reply(user_id, conv_id)
            assert out["channel"] == "whatsapp"
            push.assert_not_called()
            task.apply_async.assert_called_once()
            async with AsyncSessionLocal() as db:
                msg = (await db.execute(select(Message).where(Message.contact_id == cid, Message.sender == "owner"))).scalar_one()
                assert (msg.channel, msg.status) == (None, "queued")
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_customer_chatting_on_the_web_right_now_gets_it_there(self):
        user_id, _, conv_id = await _seed(web_minutes_ago=5)
        try:
            out, _, task = await _reply(user_id, conv_id)
            assert out["channel"] == "web"
            task.apply_async.assert_not_called()
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_stale_web_and_dead_push_fall_back_to_whatsapp(self):
        user_id, _, conv_id = await _seed(push=True, web_minutes_ago=120)
        try:
            out, push, task = await _reply(user_id, conv_id, accepted=0)
            push.assert_awaited_once()
            assert out["channel"] == "whatsapp"
            task.apply_async.assert_called_once()
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_owner_can_force_whatsapp(self):
        user_id, _, conv_id = await _seed(push=True, web_minutes_ago=1)
        try:
            out, push, task = await _reply(user_id, conv_id, channel="whatsapp")
            assert out["channel"] == "whatsapp"
            push.assert_not_called()
            task.apply_async.assert_called_once()
        finally:
            await _cleanup(user_id)


async def _web_chat(user_id, cid, text, rag_reply="Abrimos de 9 a 9."):
    redis = FakeRedis()
    session = str(uuid.uuid4())
    await redis.setex(f"{SESSION_CONTACT_REDIS_PREFIX}{user_id}:{session}", 60, str(cid))
    rag = AsyncMock(return_value=rag_reply)
    with patch("app.services.rag_service.answer_with_rag", rag), \
            patch("app.services.realtime.publish_conversation_event", AsyncMock()):
        async with AsyncSessionLocal() as db:
            out = await widget_chat(request=_request(), advertiser_id=user_id,
                                    body={"message": text, "session_id": session}, db=db, redis=redis)
    return out, rag


class TestWebChatInTheInbox:
    @pytest.mark.asyncio
    async def test_web_turns_land_in_the_same_conversation(self):
        user_id, cid, conv_id = await _seed()
        try:
            out, _ = await _web_chat(user_id, cid, "¿a qué hora abren?")
            assert out["reply"] == "Abrimos de 9 a 9."
            async with AsyncSessionLocal() as db:
                conv = await db.get(Conversation, conv_id)
                assert conv.messages[-2:] == [
                    {"role": "user", "content": "¿a qué hora abren?", "channel": "web"},
                    {"role": "assistant", "content": "Abrimos de 9 a 9.", "channel": "web"},
                ]
                assert conv.messages[0]["content"] == "hola por WhatsApp"  # una sola plática
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_web_only_customer_gets_a_conversation(self):
        user_id, cid, conv_id = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(delete(Conversation).where(Conversation.id == conv_id))
                await db.commit()
            await _web_chat(user_id, cid, "hola")
            async with AsyncSessionLocal() as db:
                conv = (await db.execute(select(Conversation).where(Conversation.contact_id == cid))).scalar_one()
                assert len(conv.messages) == 2 and conv.status == "active"
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_paused_bot_stays_quiet_on_the_web_too(self):
        user_id, cid, conv_id = await _seed(status="escalated")
        try:
            alert = AsyncMock(return_value=True)
            with patch("app.services.owner_alerts.alert_web_message", alert):
                out, rag = await _web_chat(user_id, cid, "¿me atiende alguien?")
            assert out["handoff"] is True and out["reply"] == ""
            rag.assert_not_called()
            assert alert.await_args.args[2:] == (cid, "Ana", "¿me atiende alguien?")
            async with AsyncSessionLocal() as db:
                conv = await db.get(Conversation, conv_id)
                assert conv.messages[-1] == {"role": "user", "content": "¿me atiende alguien?", "channel": "web"}
                rows = (await db.execute(select(Message).where(Message.contact_id == cid))).scalars().all()
                assert [(m.direction, m.channel) for m in rows] == [("inbound", "web")]
        finally:
            await _cleanup(user_id)


class TestPortalHistory:
    @pytest.mark.asyncio
    async def test_one_thread_without_campaigns_or_internal_markers(self):
        user_id, cid, _ = await _seed()
        other_id, other_cid, _ = await _seed()
        try:
            now = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as db:
                camp = Campaign(advertiser_id=user_id, name="Promo", type="promo", message_text="x")
                db.add(camp)
                await db.flush()

                def m(direction, content, minutes, **kw):
                    return Message(advertiser_id=user_id, contact_id=cid, direction=direction, content=content,
                                   status="sent", created_at=now - timedelta(minutes=minutes), **kw)

                db.add_all([
                    m("inbound", "hola por WhatsApp", 30),
                    m("outbound", "¡Hola! ¿En qué te ayudo?", 29),
                    m("outbound", "[AUDIO] https://cdn/x.mp3", 28),
                    m("outbound", "Promo de corte", 27, campaign_id=camp.id),
                    m("inbound", "¿precio?", 10, channel="web"),
                    m("outbound", "Te lo confirmo yo", 2, channel="web", sender="owner"),
                    Message(advertiser_id=other_id, contact_id=other_cid, direction="inbound", content="de otro",
                            status="sent"),
                ])
                await db.commit()
            async with AsyncSessionLocal() as db:
                out = await get_messages(request=_request(), token=make_portal_token(cid), db=db)
            assert [(x["content"], x["channel"], x["from_owner"]) for x in out["messages"]] == [
                ("hola por WhatsApp", "whatsapp", False),
                ("¡Hola! ¿En qué te ayudo?", "whatsapp", False),
                ("¿precio?", "web", False),
                ("Te lo confirmo yo", "web", True),
            ]
            after = (now - timedelta(minutes=5)).isoformat()
            async with AsyncSessionLocal() as db:
                out = await get_messages(request=_request(), token=make_portal_token(cid), after=after, db=db)
            assert [x["content"] for x in out["messages"]] == ["Te lo confirmo yo"]
        finally:
            await _cleanup(user_id)
            await _cleanup(other_id)
