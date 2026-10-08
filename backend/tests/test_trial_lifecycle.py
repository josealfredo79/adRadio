"""Fin de la prueba gratis (trial_lifecycle.py): pausa, +5 días si se está
usando, cuentas exentas, y que en pausa el bot no use IA (web y WhatsApp)."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete
from starlette.requests import Request

from app.api.v1.widget import widget_chat
from app.core.redis import close_redis
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.services.inbound_pipeline import InboundMessage, process_inbound_message
from app.services.trial_lifecycle import (
    extend_active_trials,
    is_paused,
    paused_reply,
    trial_days_left,
)

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
PHONE = "+525511118888"


def _user(**kw) -> User:
    base = {"email": "x@test.com", "business_name": "Tacos El Güero", "subscription_status": "trial",
            "billing_exempt": False, "plan_expires_at": NOW - timedelta(hours=1)}
    base.update(kw)
    return User(**base)


class TestIsPaused:
    def test_expired_trial_is_paused(self):
        assert is_paused(_user(), NOW)

    def test_trial_still_running_is_not(self):
        assert not is_paused(_user(plan_expires_at=NOW + timedelta(days=3)), NOW)

    def test_unverified_trial_without_date_is_not(self):
        assert not is_paused(_user(plan_expires_at=None), NOW)

    def test_exempt_account_never_pauses(self):
        assert not is_paused(_user(billing_exempt=True), NOW)
        assert not is_paused(_user(billing_exempt=True, subscription_status="churned"), NOW)

    def test_churned_and_suspended_are_paused(self):
        assert is_paused(_user(subscription_status="churned", plan_expires_at=None), NOW)
        assert is_paused(_user(subscription_status="suspended", plan_expires_at=None), NOW)

    def test_paying_account_is_not(self):
        assert not is_paused(_user(subscription_status="active", plan_expires_at=NOW + timedelta(days=20)), NOW)


class TestDaysLeftAndReply:
    def test_days_left_rounds_up(self):
        assert trial_days_left(_user(plan_expires_at=NOW + timedelta(days=2, hours=1)), NOW) == 3
        assert trial_days_left(_user(), NOW) == 0
        assert trial_days_left(_user(billing_exempt=True), NOW) is None
        assert trial_days_left(_user(subscription_status="active"), NOW) is None

    def test_reply_never_shows_owner_personal_phone(self):
        reply = paused_reply(_user(phone="+525599999999", meta_connection_status="not_connected"))
        assert "Tacos El Güero" in reply and "9999" not in reply
        connected = paused_reply(_user(meta_connection_status="connected", meta_display_phone_number="+52 55 1234 5678"))
        assert "+52 55 1234 5678" in connected


async def _seed(**kw) -> uuid.UUID:
    await engine.dispose()
    await close_redis()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Tacos El Güero",
                    subscription_status="trial", **kw)
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(*user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Message).where(Message.advertiser_id.in_(user_ids)))
        await db.execute(delete(Conversation).where(Conversation.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()
    await close_redis()


class TestExtendActiveTrials:
    @pytest.mark.asyncio
    async def test_used_trial_gets_five_days_once_and_unused_stays_paused(self):
        now = datetime.now(timezone.utc)
        used = await _seed(plan_expires_at=now - timedelta(hours=2))
        idle = await _seed(plan_expires_at=now - timedelta(hours=2))
        seen = await _seed(plan_expires_at=now - timedelta(hours=2), last_seen_at=now - timedelta(days=1))
        exempt = await _seed(plan_expires_at=now - timedelta(hours=2), billing_exempt=True,
                             last_seen_at=now - timedelta(days=1))
        try:
            async with AsyncSessionLocal() as db:
                contact = Contact(advertiser_id=used, name="Ana", phone=PHONE, source="landing")
                db.add(contact)
                await db.flush()
                db.add(Message(advertiser_id=used, contact_id=contact.id, direction="inbound",
                               content="hola", channel="web"))
                await db.commit()
                assert await extend_active_trials(db, now) == 2  # used + seen
            async with AsyncSessionLocal() as db:
                u, i, s, e = [await db.get(User, x) for x in (used, idle, seen, exempt)]
                assert u.trial_extended_at and u.plan_expires_at > now + timedelta(days=4)
                assert s.trial_extended_at and not is_paused(s)
                assert i.trial_extended_at is None and is_paused(i)
                assert e.trial_extended_at is None and not is_paused(e)
                # Una sola vez: al volver a vencer ya no hay otra extensión.
                u.plan_expires_at = now - timedelta(hours=1)
                await db.commit()
                assert await extend_active_trials(db, now) == 0
        finally:
            await _cleanup(used, idle, seen, exempt)

    @pytest.mark.asyncio
    async def test_long_expired_trials_are_not_reviewed(self):
        now = datetime.now(timezone.utc)
        old = await _seed(plan_expires_at=now - timedelta(days=10), last_seen_at=now - timedelta(hours=1))
        try:
            async with AsyncSessionLocal() as db:
                assert await extend_active_trials(db, now) == 0
        finally:
            await _cleanup(old)


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/widget/chat/x", "headers": [],
                    "client": (f"test-{uuid.uuid4()}", 123), "query_string": b""})


class TestPausedBotUsesNoAI:
    @pytest.mark.asyncio
    async def test_web_chat_gets_fixed_reply(self):
        user_id = await _seed(plan_expires_at=datetime.now(timezone.utc) - timedelta(days=1))
        try:
            with patch("app.services.rag_service.answer_with_rag", new_callable=AsyncMock) as rag:
                async with AsyncSessionLocal() as db:
                    out = await widget_chat(request=_request(), advertiser_id=user_id,
                                            body={"message": "¿tienen tacos?"}, db=db, redis=None)
            assert "no estamos atendiendo en línea" in out["reply"]
            rag.assert_not_called()
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_whatsapp_gets_fixed_reply(self):
        user_id = await _seed(plan_expires_at=datetime.now(timezone.utc) - timedelta(days=1))
        try:
            send = AsyncMock(return_value=("wamid.fake", None))
            with patch("app.services.rag_service.answer_with_rag", new_callable=AsyncMock) as rag, \
                 patch("app.services.inbound_pipeline.get_redis_optional", new=AsyncMock(return_value=None)):
                async with AsyncSessionLocal() as db:
                    advertiser = await db.get(User, user_id)
                    await process_inbound_message(
                        db, InboundMessage(advertiser=advertiser, from_number=PHONE, body_text="hola"),
                        send=send, send_owner=send,
                    )
            send.assert_awaited_once()
            assert "no estamos atendiendo en línea" in send.await_args.args[1]
            rag.assert_not_called()
        finally:
            await _cleanup(user_id)
