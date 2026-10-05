"""Agente 3D en la página pública (/sitio/:slug): voz para visitantes, el
dato de si el registro con código está encendido, y el aviso de que el bot
necesita sus datos para pedir/agendar (el chat ofrece registrarse)."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete
from starlette.requests import Request

from app.api.v1.public_site import get_public_site, site_listen, site_speak
from app.api.v1.widget import widget_chat
from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.user import User
from tests.test_portal_web_shift import FakeRedis as _FakeRedis


class FakeRedis(_FakeRedis):
    async def setex(self, k, ttl, v):
        self.store[k] = v


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/public/site/x", "headers": [],
                    "client": (f"test-{uuid.uuid4()}", 1), "query_string": b""})


async def _seed():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Tacos",
                    slug=f"tacos-{uuid.uuid4().hex[:8]}")
        db.add(user)
        await db.commit()
        return user.id, user.slug


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_site_tells_the_page_its_slug_and_if_sign_up_is_on(monkeypatch):
    user_id, slug = await _seed()
    try:
        monkeypatch.setattr(settings, "CUSTOMER_ACCOUNT_ENABLED", True)
        async with AsyncSessionLocal() as db:
            site = await get_public_site(request=_request(), slug=slug, db=db)
        assert site["slug"] == slug and site["account_available"] is True
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_voice_needs_a_real_page_and_speaks_with_edge_tts():
    user_id, slug = await _seed()
    try:
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc:
                await site_speak(request=_request(), slug="no-existe-" + uuid.uuid4().hex, body={"text": "hola"}, db=db)
            assert exc.value.status_code == 404
            with patch("app.services.radio.tts._tts_edge", AsyncMock(return_value=b"mp3")) as tts:
                resp = await site_speak(request=_request(), slug=slug, body={"text": "**Hola** amigo"}, db=db)
            assert resp.body == b"mp3" and tts.await_args.args[0] == "Hola amigo"
            with patch("app.api.v1.voice_setup.read_transcript", AsyncMock(return_value="quiero tacos")):
                out = await site_listen(request=_request(), slug=slug, audio=None, text="x", db=db)
            assert out["transcript"] == "quiero tacos"
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_anonymous_visitor_ordering_gets_the_needs_contact_flag():
    user_id, _ = await _seed()
    try:
        async with AsyncSessionLocal() as db:
            out = await widget_chat(request=_request(), advertiser_id=user_id,
                                    body={"message": "quiero hacer un pedido de 3 tacos"}, db=db, redis=FakeRedis())
        assert out["needs_contact"] is True
        with patch("app.services.rag_service.answer_with_rag", AsyncMock(return_value="Abrimos a las 9.")):
            async with AsyncSessionLocal() as db:
                out = await widget_chat(request=_request(), advertiser_id=user_id,
                                        body={"message": "¿a qué hora abren?"}, db=db, redis=FakeRedis())
        assert out["needs_contact"] is False
    finally:
        await _cleanup(user_id)


def test_the_chat_quick_order_button_is_an_order():
    from app.services.claude_service import detect_order_intent

    assert detect_order_intent("Quiero hacer un pedido") is True
    assert detect_order_intent("hago un pedido de 3 tacos") is True
    assert detect_order_intent("¿dónde va mi pedido?") is False
