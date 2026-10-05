"""Agente del cliente (customer_agent.py) con Claude simulado — real-DB para
lo que importa: que solo ejecute con el "sí" del cliente, que no toque datos
de otro cliente, y que si Claude falla el chat siga con los flujos fijos."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx
import pytest
from sqlalchemy import delete, select
from starlette.requests import Request

from app.api.v1.widget import SESSION_CONTACT_REDIS_PREFIX, widget_chat
from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.loyalty_stamp import LoyaltyStamp
from app.models.message import Message
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.user import User
from app.services import customer_agent as agent
from app.services.availability_service import TZ
from tests.test_portal_web_shift import FakeRedis as _FakeRedis


class Redis(_FakeRedis):
    async def setex(self, k, ttl, v):
        self.store[k] = v

    async def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-agent")
    monkeypatch.setattr("app.services.plan_usage.register_bot_conversation", AsyncMock())


def tool(name, **args):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=f"tu_{uuid.uuid4().hex[:6]}")


def text(t):
    return SimpleNamespace(type="text", text=t)


def resp(*blocks, stop="tool_use"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop)


def tool_results(client) -> list[dict]:
    """Todo lo que las herramientas le devolvieron a Claude, en orden (la
    lista de mensajes es la misma en cada llamada: se lee al final)."""
    messages = client.messages.create.await_args_list[-1].kwargs["messages"]
    return [json.loads(block["content"]) for m in messages if isinstance(m["content"], list)
            for block in m["content"] if isinstance(block, dict) and block.get("type") == "tool_result"]


def fake_claude(*responses):
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=list(responses))
    return patch("app.services.customer_agent._get_client", return_value=client), client


def _next_open_day() -> datetime:
    """Mañana o el siguiente día hábil (lunes a viernes 9–18 por defecto)."""
    day = datetime.now(TZ).date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, 17, 0, tzinfo=TZ)


async def _seed(enabled=True):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Tacos El Primo",
                    customer_agent_enabled=enabled,
                    loyalty_config={"enabled": True, "stamps_required": 5, "reward": "Orden gratis"})
        db.add(user)
        await db.flush()
        ana = Contact(advertiser_id=user.id, name="Ana López", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        beto = Contact(advertiser_id=user.id, name="Beto", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        db.add_all([ana, beto])
        await db.flush()
        pastor = Product(advertiser_id=user.id, name="Taco al pastor", price=25, active=True)
        db.add(pastor)
        beto_appt = Appointment(advertiser_id=user.id, contact_id=beto.id, customer_name="Beto", service="Mesa",
                                scheduled_at=datetime.now(timezone.utc) + timedelta(days=3), status="confirmed")
        db.add(beto_appt)
        await db.commit()
        return user.id, ana.id, pastor.id, beto_appt.id


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        orders = select(Order.id).where(Order.advertiser_id == user_id)
        await db.execute(delete(OrderItem).where(OrderItem.order_id.in_(orders)))
        for model in (LoyaltyStamp, Order, Appointment, Message, Conversation, Product, Contact):
            await db.execute(delete(model).where(model.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


async def _say(user_id, contact_id, message, redis, claude=None):
    async with AsyncSessionLocal() as db:
        user, contact = await db.get(User, user_id), await db.get(Contact, contact_id)
        with patch("app.services.appointment_booking_service._notify_owner", AsyncMock()), \
                patch("app.services.widget_order_service._notify_owner", AsyncMock()), \
                patch("app.services.customer_agent._owner_text", AsyncMock()):
            if claude:
                with claude:
                    return await agent.handle(db, redis, user, contact, message, [])
            return await agent.handle(db, redis, user, contact, message, [])


class TestRouting:
    @pytest.mark.parametrize("msg", ["¿tienes lugar el viernes en la tarde?", "quiero agendar una cita",
                                     "cámbiame la cita, quiero cancelar mi cita", "¿cuántos sellos llevo?",
                                     "mándame 2 de pastor para llevar", "quiero hacer un pedido"])
    def test_actions_go_to_the_agent(self, msg):
        assert agent.wants_action(msg) is True

    @pytest.mark.parametrize("msg", ["hola", "¿a qué hora abren?", "¿dónde están?", "gracias"])
    def test_simple_questions_stay_on_the_cheap_chain(self, msg):
        assert agent.wants_action(msg) is False

    @pytest.mark.asyncio
    async def test_off_or_without_key_does_nothing(self, monkeypatch):
        user_id, ana, *_ = await _seed(enabled=False)
        try:
            assert await _say(user_id, ana, "quiero agendar", Redis()) is None
            async with AsyncSessionLocal() as db:
                (await db.get(User, user_id)).customer_agent_enabled = True
                await db.commit()
            monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
            assert await _say(user_id, ana, "quiero agendar", Redis()) is None
        finally:
            await _cleanup(user_id)


class TestBooking:
    @pytest.mark.asyncio
    async def test_proposes_then_books_only_after_yes(self):
        user_id, ana, *_ = await _seed()
        r = Redis()
        when = _next_open_day()
        try:
            claude, client = fake_claude(
                resp(tool("horarios_libres", fecha=when.date().isoformat())),
                resp(tool("proponer_cita", servicio="Mesa para 4", fecha_hora=when.strftime("%Y-%m-%dT%H:%M"))),
                resp(text("Tengo a las 5 pm. ¿Lo confirmo?"), stop="end_turn"),
            )
            out = await _say(user_id, ana, "¿tienes lugar mañana en la tarde para 4?", r, claude)
            assert out.text.endswith("¿Lo confirmo?") and out.confirm is True
            # Los resultados de las herramientas le llegan a Claude.
            assert "17:00" in tool_results(client)[0]["horarios"]
            async with AsyncSessionLocal() as db:
                assert (await db.execute(select(Appointment).where(Appointment.contact_id == ana))).first() is None

            out = await _say(user_id, ana, "sí", r)
            assert out.text.startswith("✅ ¡Listo! Tu cita de Mesa para 4") and out.confirm is False
            async with AsyncSessionLocal() as db:
                appt = (await db.execute(select(Appointment).where(Appointment.contact_id == ana))).scalar_one()
            assert appt.scheduled_at.astimezone(TZ) == when and appt.status == "confirmed"
            assert not any(k.startswith(agent.PENDING_PREFIX) for k in r.store)
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_no_cancels_the_proposal(self):
        user_id, ana, *_ = await _seed()
        r = Redis()
        when = _next_open_day()
        try:
            claude, _ = fake_claude(
                resp(tool("proponer_cita", servicio="Corte", fecha_hora=when.strftime("%Y-%m-%dT%H:%M"))),
                resp(text("¿Lo confirmo?"), stop="end_turn"),
            )
            await _say(user_id, ana, "agéndame mañana a las 5", r, claude)
            out = await _say(user_id, ana, "no", r)
            assert "no lo hago" in out.text
            async with AsyncSessionLocal() as db:
                assert (await db.execute(select(Appointment).where(Appointment.contact_id == ana))).first() is None
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_cannot_touch_another_customers_appointment(self):
        user_id, ana, _, beto_appt = await _seed()
        r = Redis()
        try:
            claude, client = fake_claude(
                resp(tool("proponer_cancelar_cita", cita_id=str(beto_appt))),
                resp(text("No encontré esa cita."), stop="end_turn"),
            )
            out = await _say(user_id, ana, "cancela mi cita " + str(beto_appt), r, claude)
            assert "error" in tool_results(client)[0] and out.confirm is False
            assert not any(k.startswith(agent.PENDING_PREFIX) for k in r.store)
            # Y ni con un "sí" después se cancela nada.
            await _say(user_id, ana, "sí", r)
            async with AsyncSessionLocal() as db:
                assert (await db.get(Appointment, beto_appt)).status == "confirmed"
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_taken_slot_is_refused(self):
        user_id, ana, *_ = await _seed()
        when = _next_open_day()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Appointment(advertiser_id=user_id, customer_name="X", service="X", scheduled_at=when,
                                   status="confirmed"))
                await db.commit()
            claude, _ = fake_claude(
                resp(tool("proponer_cita", servicio="Corte", fecha_hora=when.strftime("%Y-%m-%dT%H:%M"))),
                resp(text("Ese horario ya no está, ¿otro?"), stop="end_turn"),
            )
            out = await _say(user_id, ana, "agéndame mañana a las 5", Redis(), claude)
            assert out.confirm is False
        finally:
            await _cleanup(user_id)


class TestOrders:
    @pytest.mark.asyncio
    async def test_order_with_catalog_products_and_stamp(self):
        user_id, ana, pastor, _ = await _seed()
        r = Redis()
        try:
            claude, _ = fake_claude(
                resp(tool("buscar_productos", texto="pastor")),
                resp(tool("proponer_pedido", productos=[{"producto_id": str(pastor), "cantidad": 2}],
                          entrega="recoger", pago="Efectivo")),
                resp(text("2 tacos al pastor para recoger, $50. ¿Lo confirmo?"), stop="end_turn"),
            )
            out = await _say(user_id, ana, "mándame 2 de pastor para llevar", r, claude)
            assert out.confirm is True
            out = await _say(user_id, ana, "Sí, confírmalo", r)
            assert "Pedido #0001 confirmado" in out.text and "2 Taco al pastor" in out.text
            assert "Sumaste un sello" in out.text
            async with AsyncSessionLocal() as db:
                order = (await db.execute(select(Order).where(Order.contact_id == ana))).scalar_one()
                items = (await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))).scalars().all()
            assert order.state == "confirmed" and [(i.product_id, i.quantity) for i in items] == [(pastor, 2)]
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_delivery_needs_an_address(self):
        user_id, ana, pastor, _ = await _seed()
        try:
            claude, client = fake_claude(
                resp(tool("proponer_pedido", productos=[{"producto_id": str(pastor), "cantidad": 1}],
                          entrega="domicilio", pago="Efectivo")),
                resp(text("¿A qué dirección te lo mando?"), stop="end_turn"),
            )
            out = await _say(user_id, ana, "quiero pedir uno a domicilio", Redis(), claude)
            assert "dirección" in tool_results(client)[0]["error"] and out.confirm is False
        finally:
            await _cleanup(user_id)


class TestFallback:
    @pytest.mark.asyncio
    async def test_claude_down_means_fixed_flows(self):
        user_id, ana, *_ = await _seed()
        try:
            client = MagicMock()
            client.messages.create = AsyncMock(side_effect=anthropic.APIConnectionError(
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")))
            with patch("app.services.customer_agent._get_client", return_value=client):
                assert await _say(user_id, ana, "quiero agendar una cita", Redis()) is None
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_web_chat_uses_the_agent_and_flags_the_confirmation(self):
        user_id, ana, *_ = await _seed()
        r = Redis()
        when = _next_open_day()
        session = str(uuid.uuid4())
        r.store[f"{SESSION_CONTACT_REDIS_PREFIX}{user_id}:{session}"] = str(ana)
        try:
            claude, _ = fake_claude(
                resp(tool("proponer_cita", servicio="Corte", fecha_hora=when.strftime("%Y-%m-%dT%H:%M"))),
                resp(text("¿Lo confirmo?"), stop="end_turn"),
            )
            req = Request({"type": "http", "method": "POST", "path": "/api/v1/widget/chat/x", "headers": [],
                           "client": (f"test-{uuid.uuid4()}", 1), "query_string": b""})
            with claude, patch("app.services.realtime.publish_conversation_event", AsyncMock()):
                async with AsyncSessionLocal() as db:
                    out = await widget_chat(request=req, advertiser_id=user_id,
                                            body={"message": "agéndame mañana a las 5", "session_id": session},
                                            db=db, redis=r)
            # "¿Lo confirmo?" a secas no dice qué: el código le pone el resumen real.
            assert out["reply"].startswith("Te lo preparo así: Corte, el ") and out["confirm"] is True
        finally:
            await _cleanup(user_id)
