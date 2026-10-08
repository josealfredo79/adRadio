"""Hueco cerrado 2026-10-04: "Dejar mis datos" del widget ligaba la sesión al
contacto de CUALQUIER número escrito, sin verificar, y la confirmación de un
pedido traía el link de la tarjeta (/c/...) de esa persona — con sus citas y
su plática. Ahora: número existente → no se liga; número nuevo → se liga sin
verificar y nunca recibe links de tarjeta."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select
from starlette.requests import Request

from app.api.v1.widget import (
    SESSION_CONTACT_REDIS_PREFIX,
    UNVERIFIED_SESSION_PREFIX,
    widget_capture_lead,
    widget_chat,
)
from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.order import Order
from app.models.user import User
from tests.test_portal_web_shift import FakeRedis


class Redis(FakeRedis):
    async def setex(self, k, ttl, v):
        self.store[k] = v


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-widget-lead")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://www.iaradio.online")


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/widget/x", "headers": [],
                    "client": (f"test-{uuid.uuid4()}", 1), "query_string": b""})


async def _seed():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Tacos")
        db.add(user)
        await db.flush()
        victim = Contact(advertiser_id=user.id, name="Víctima", phone="+5215512345678")
        db.add(victim)
        await db.commit()
        return user.id, victim.id


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for model in (Order, Message, Conversation, Contact):
            await db.execute(delete(model).where(model.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


async def _lead(user_id, phone, redis, session="s1"):
    with patch("app.services.webhook_dispatcher.dispatch_webhook_event", AsyncMock()):
        async with AsyncSessionLocal() as db:
            return await widget_capture_lead(request=_request(), advertiser_id=user_id,
                                             body={"name": "Intruso", "phone": phone, "session_id": session},
                                             db=db, redis=redis)


async def _finish_order(user_id, contact_id, redis, session="s1"):
    async with AsyncSessionLocal() as db:
        db.add(Order(advertiser_id=user_id, contact_id=contact_id, order_number=1, state="collecting_payment",
                     items_raw="tacos", customer_name="X", delivery_address="Centro"))
        await db.commit()
    with patch("app.services.widget_order_service._notify_owner", AsyncMock()), \
            patch("app.services.realtime.publish_conversation_event", AsyncMock()):
        async with AsyncSessionLocal() as db:
            out = await widget_chat(request=_request(), advertiser_id=user_id,
                                    body={"message": "Efectivo", "session_id": session}, db=db, redis=redis)
    return out["reply"]


class TestLeadCapture:
    @pytest.mark.asyncio
    async def test_someone_elses_number_is_not_linked(self):
        user_id, victim_id = await _seed()
        r = Redis()
        try:
            # Mismo número en otro formato: igual se reconoce.
            out = await _lead(user_id, "+525512345678", r)
            assert out["existing"] is True
            assert not any(k.startswith(SESSION_CONTACT_REDIS_PREFIX) for k in r.store)
            async with AsyncSessionLocal() as db:
                contacts = (await db.execute(select(Contact).where(Contact.advertiser_id == user_id))).scalars().all()
                conv = (await db.execute(select(Conversation).where(Conversation.contact_id == victim_id))).first()
            assert [c.id for c in contacts] == [victim_id] and conv is None
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_new_number_can_order_but_never_gets_a_card_link(self):
        user_id, _ = await _seed()
        r = Redis()
        try:
            out = await _lead(user_id, "+525587654321", r)
            assert out["message"] == "ok"
            assert r.store.get(f"{UNVERIFIED_SESSION_PREFIX}{user_id}:s1") == "1"
            reply = await _finish_order(user_id, uuid.UUID(out["contact_id"]), r)
            assert "Pedido #0001 confirmado" in reply and "/c/" not in reply
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_portal_session_order_confirmation_has_no_link(self):
        """Desde 2026-10-07 la confirmación en el chat web no trae el link del
        portal a nadie: el cliente ya está en su chat (en WhatsApp sí va)."""
        user_id, victim_id = await _seed()
        r = Redis()
        try:
            r.store[f"{SESSION_CONTACT_REDIS_PREFIX}{user_id}:p1"] = str(victim_id)  # como /chat-session del portal
            reply = await _finish_order(user_id, victim_id, r, session="p1")
            assert reply and "/c/" not in reply
        finally:
            await _cleanup(user_id)
