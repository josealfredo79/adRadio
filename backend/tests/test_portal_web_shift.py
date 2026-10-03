"""De WhatsApp a la web (Meta cobra desde 2026-10-01):
1. El bot invita a seguir en el portal una vez al día por cliente, en la
   plática normal, dentro del mismo mensaje.
2. El chat web de un cliente que entró desde su portal queda guardado como
   canal "web", y el Dashboard lo cuenta aparte de WhatsApp (BD real)."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select
from starlette.requests import Request

from app.api.v1.widget import SESSION_CONTACT_REDIS_PREFIX, widget_chat
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.message import Message
from app.models.user import User
from app.services import portal_service as ps


class FakeRedis:
    def __init__(self):
        self.store: dict = {}

    async def incr(self, k):
        self.store[k] = int(self.store.get(k, 0)) + 1
        return self.store[k]

    async def expire(self, k, ttl):
        return True

    async def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v
        return True

    async def get(self, k):
        return self.store.get(k)

    async def setex(self, k, ttl, v):
        self.store[k] = v


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(ps.settings, "SECRET_KEY", "test-secret")


class TestDailyInvite:
    @pytest.mark.asyncio
    async def test_third_message_of_the_day_gets_one_invite(self):
        r, cid = FakeRedis(), uuid.uuid4()
        out = [await ps.maybe_portal_invite(r, cid, "hola", "¡Hola!") for _ in range(5)]
        assert out[:2] == ["", ""]
        assert out[2].startswith("\n\n💬") and f"/c/{ps.make_portal_token(cid)}" in out[2]
        assert out[3:] == ["", ""]  # una sola vez al día

    @pytest.mark.asyncio
    async def test_asking_prices_invites_right_away(self):
        out = await ps.maybe_portal_invite(FakeRedis(), uuid.uuid4(), "¿Cuánto cuesta el corte?", "Cuesta $150.")
        assert "💬" in out

    @pytest.mark.asyncio
    async def test_no_invite_when_the_reply_already_has_the_link_or_no_redis(self):
        cid = uuid.uuid4()
        assert await ps.maybe_portal_invite(FakeRedis(), cid, "precio", f"Listo {ps.portal_url(cid)}") == ""
        assert await ps.maybe_portal_invite(None, cid, "precio", "Cuesta $150.") == ""
        assert await ps.maybe_portal_invite(FakeRedis(), None, "precio", "Cuesta $150.") == ""


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/widget/chat/x", "headers": [],
                    "client": (f"test-{uuid.uuid4()}", 1), "query_string": b""})


@pytest.mark.asyncio
async def test_portal_chat_is_saved_as_web_and_counted_apart_from_whatsapp():
    from app.api.v1.profile import dashboard

    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Tacos El Primo")
        db.add(user)
        await db.commit()
        contact = Contact(advertiser_id=user.id, name="Ana", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        db.add(contact)
        await db.flush()
        db.add(Message(advertiser_id=user.id, contact_id=contact.id, direction="outbound", content="hola por WA",
                       status="sent", sent_at=datetime.now(timezone.utc)))
        await db.commit()
        uid, cid = user.id, contact.id
    try:
        redis = FakeRedis()
        session = str(uuid.uuid4())
        await redis.setex(f"{SESSION_CONTACT_REDIS_PREFIX}{uid}:{session}", 60, str(cid))
        with patch("app.services.rag_service.answer_with_rag", AsyncMock(return_value="Abrimos de 9 a 9.")), \
                patch("app.services.realtime.publish_conversation_event", AsyncMock()):
            async with AsyncSessionLocal() as db:
                out = await widget_chat(request=_request(), advertiser_id=uid,
                                        body={"message": "¿a qué hora abren?", "session_id": session}, db=db, redis=redis)
        assert out["reply"] == "Abrimos de 9 a 9."
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(Message).where(Message.contact_id == cid).order_by(Message.created_at))).scalars().all()
            assert [(m.direction, m.channel) for m in rows] == [("outbound", None), ("inbound", "web"), ("outbound", "web")]
            user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
            data = await dashboard(db=db, current_user=user, redis=None)
        assert data["web_replies_this_month"] == 1
        assert data["messages_sent_this_month"] == 1  # solo el de WhatsApp
    finally:
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Message).where(Message.advertiser_id == uid))
            await db.execute(delete(Contact).where(Contact.advertiser_id == uid))
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
        await engine.dispose()


class TestPortalVoice:
    """Hablar en el chat del portal: el link es la credencial."""

    @pytest.mark.asyncio
    async def test_listen_and_speak_need_a_valid_link(self):
        from fastapi import HTTPException

        from app.api.v1.portal import portal_listen, portal_speak

        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as e:
                await portal_listen(request=_request(), token="no-vale", audio=None, text="hola", db=db)
            assert e.value.status_code == 404
            with pytest.raises(HTTPException) as e:
                await portal_speak(request=_request(), token="no-vale", body={"text": "hola"}, db=db)
            assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_audio_is_transcribed_and_reply_is_spoken(self):
        from io import BytesIO

        from fastapi import UploadFile
        from starlette.datastructures import Headers

        from app.api.v1 import portal

        contact, advertiser = Contact(id=uuid.uuid4()), User(id=uuid.uuid4())
        audio = UploadFile(file=BytesIO(b"webm"), filename="v.webm", headers=Headers({"content-type": "audio/webm"}))
        with patch.object(portal, "_resolve", AsyncMock(return_value=(contact, advertiser))), \
                patch("app.api.v1.voice_setup.transcribe_audio_bytes", AsyncMock(return_value="¿cuánto cuesta el corte?")), \
                patch("app.services.radio.tts._tts_edge", AsyncMock(return_value=b"mp3")) as tts:
            out = await portal.portal_listen(request=_request(), token="t", audio=audio, text=None, db=None)
            assert out == {"transcript": "¿cuánto cuesta el corte?"}
            res = await portal.portal_speak(request=_request(), token="t", body={"text": "El *corte* cuesta $150."}, db=None)
        assert res.body == b"mp3" and res.media_type == "audio/mpeg"
        assert tts.await_args.args[0] == "El corte cuesta $150."
