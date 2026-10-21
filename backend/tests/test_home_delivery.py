"""Entrega a domicilio sí/no (spec docs/specs/2026-10-20-entrega-a-domicilio.md).
Lo encontró la simulación del 2026-10-20: el agente confirmó "Pedido #0001 … a
domicilio" en una estética que no entrega. Un caso de la spec por prueba."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.api.v1.profile import update_profile
from app.core.redis import close_redis
from app.database import AsyncSessionLocal, engine
from app.models.order import Order
from app.models.user import User
from app.schemas.profile import ProfileUpdate
from app.services import customer_agent as agent
from app.services.copilot_service import (
    CONFIRM_TOOLS,
    _execute_confirm_tool,
    _preview_confirm_tool,
)
from app.services.inbound_pipeline import InboundMessage, process_inbound_message
from app.services.widget_order_service import handle_widget_order
from tests.test_customer_agent import (
    Redis,
    _cleanup,
    _keys,  # noqa: F401 — fixture autouse: sin él el agente no se enciende (no hay modelo con herramientas)
    _say,
    fake_claude,
    resp,
    text,
    tool,
    tool_results,
)
from tests.test_customer_agent import _seed as _seed_agent


async def _seed(delivers_home):
    user_id, ana, pastor, _ = await _seed_agent(delivers_home=delivers_home)
    return user_id, ana, pastor


async def _orders(user_id) -> list[Order]:
    async with AsyncSessionLocal() as db:
        return list((await db.execute(select(Order).where(Order.advertiser_id == user_id))).scalars())


def _home_order(pastor):
    return tool("proponer_pedido", productos=[{"producto_id": str(pastor), "cantidad": 1}],
                entrega="domicilio", direccion="Calle Morelos 45", pago="Efectivo")


class TestAgent:
    @pytest.mark.asyncio
    async def test_caso1_delivers_asks_and_takes_the_address(self):
        user_id, ana, pastor = await _seed(True)
        r = Redis()
        try:
            claude, client = fake_claude(resp(_home_order(pastor)),
                                         resp(text("1 taco a domicilio en Calle Morelos 45. ¿Lo confirmo?"), stop="end_turn"))
            out = await _say(user_id, ana, "mándame uno a Calle Morelos 45", r, claude)
            assert out.confirm is True
            assert "a domicilio (con dirección)" in str(client.messages.create.await_args_list[0].kwargs["system"])
            await _say(user_id, ana, "Sí, confírmalo", r)
            [order] = await _orders(user_id)
            assert order.state == "confirmed" and order.delivery_address == "Calle Morelos 45"
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso2_no_delivery_offers_pickup_and_no_home_order(self):
        user_id, ana, pastor = await _seed(False)
        try:
            claude, client = fake_claude(resp(_home_order(pastor)),
                                         resp(text("Solo es para recoger en el local. ¿Te lo preparo así?"), stop="end_turn"))
            out = await _say(user_id, ana, "quiero pedir uno a domicilio", Redis(), claude)
            assert "no entrega a domicilio" in tool_results(client)[0]["error"]
            assert out.confirm is False and await _orders(user_id) == []
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso3_undefined_consults_the_business_and_no_home_order(self):
        user_id, ana, pastor = await _seed(None)
        try:
            claude, client = fake_claude(resp(_home_order(pastor)),
                                         resp(text("Lo consulto con el negocio 🙏 Si quieres, también te lo preparo para recoger."),
                                              stop="end_turn"))
            out = await _say(user_id, ana, "quiero pedir uno a domicilio", Redis(), claude)
            error = tool_results(client)[0]["error"]
            assert "no ha confirmado" in error and "avisar_al_dueno" in error
            assert out.confirm is False and await _orders(user_id) == []
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("delivers", [False, None])
    async def test_caso2y3_silent_switch_to_pickup_is_said_out_loud(self, delivers):
        # Simulación 2026-10-20 (sin definir): el modelo propuso "recoger" sin decir
        # nada de la entrega que pidió el cliente, y sin avisar al negocio.
        user_id, ana, pastor = await _seed(delivers)
        try:
            claude, client = fake_claude(
                resp(tool("proponer_pedido", productos=[{"producto_id": str(pastor), "cantidad": 1}],
                          entrega="recoger", pago="Efectivo")),
                resp(text("1 taco para recoger. ¿Lo confirmo?"), stop="end_turn"),
            )
            alert = AsyncMock(return_value=True)
            with patch("app.services.owner_alerts.alert_web_message", alert):
                await _say(user_id, ana, "quiero pedir uno, me lo traen a mi casa?", Redis(), claude)
            aviso = tool_results(client)[0]["aviso"]
            assert "recoger en el local" in aviso
            assert ("ya le preguntaste al negocio" in aviso) is (delivers is None)
            assert alert.await_count == (1 if delivers is None else 0)
        finally:
            await _cleanup(user_id)

    @pytest.mark.parametrize("delivers", [False, None])
    def test_caso4_without_delivery_never_asks_home_or_pickup(self, delivers):
        rule = agent._delivery_rule(User(delivers_home=delivers))
        assert "no preguntes" in rule and "para recoger en el local" in rule
        assert "a domicilio (con dirección)" not in rule
        assert "a domicilio (con dirección)" in agent._delivery_rule(User(delivers_home=True))


class TestOrderFlowsOfAlways:
    @pytest.mark.asyncio
    async def test_caso5_web_flow_skips_the_address(self):
        user_id, ana, _ = await _seed(None)
        try:
            async with AsyncSessionLocal() as db:
                user, contact = await db.get(User, user_id), await db.get(agent.Contact, ana)
                with patch("app.services.widget_order_service._notify_owner", AsyncMock()):
                    await handle_widget_order(db, user, contact, "quiero pedir 2 tacos")
                    reply = await handle_widget_order(db, user, contact, "Ana López")
                    assert "recoger en el local" in reply and "dirección" not in reply
                    reply = await handle_widget_order(db, user, contact, "Efectivo")
            assert "Para recoger en el local" in reply
            [order] = await _orders(user_id)
            assert order.state == "confirmed" and not order.delivery_address
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso5_whatsapp_flow_skips_the_address(self):
        user_id, ana, _ = await _seed(False)
        await close_redis()
        try:
            async with AsyncSessionLocal() as db:
                contact = await db.get(agent.Contact, ana)
                db.add(Order(advertiser_id=user_id, contact_id=ana, order_number=1, state="collecting_name",
                             items_raw="2 tacos"))
                await db.commit()
                phone = contact.phone
            replies = []
            for body in ("Ana López", "Efectivo"):
                send = AsyncMock(return_value=(f"wamid.fake-{uuid.uuid4()}", None))
                async with AsyncSessionLocal() as db:
                    advertiser = await db.get(User, user_id)
                    await process_inbound_message(db, InboundMessage(advertiser=advertiser, from_number=phone,
                                                                     body_text=body), send=send, send_owner=send)
                replies.append(send.call_args_list[0].args[1])
            assert "recoger en el local" in replies[0] and "dirección" not in replies[0]
            assert "Para recoger en el local" in replies[1]
            [order] = await _orders(user_id)
            assert order.state == "confirmed" and not order.delivery_address
        finally:
            await _cleanup(user_id)
            await close_redis()


class TestOwnerSetting:
    @pytest.mark.asyncio
    async def test_caso6_settings_switch_is_saved_and_the_agent_follows_it(self):
        user_id, _, _ = await _seed(None)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                out = await update_profile(ProfileUpdate(delivers_home=True), db, user)
            assert out.delivers_home is True
            async with AsyncSessionLocal() as db:
                assert agent._delivery_rule(await db.get(User, user_id)).startswith("- Para un pedido necesitas")
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso7_copilot_changes_it_with_confirmation(self):
        user_id, _, _ = await _seed(True)
        try:
            assert "set_home_delivery" in CONFIRM_TOOLS
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                summary, resolved, err = await _preview_confirm_tool(db, user, "set_home_delivery", {"delivers": False})
                assert err is None and "solo para recoger" in summary
                assert (await db.get(User, user_id)).delivers_home is True  # nada cambia antes del "sí"
                _, err = await _execute_confirm_tool(db, user, "set_home_delivery", resolved)
            assert err is None
            async with AsyncSessionLocal() as db:
                assert (await db.get(User, user_id)).delivers_home is False
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso8_existing_businesses_start_undefined(self):
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x")
            db.add(user)
            await db.commit()
            user_id = user.id
        try:
            async with AsyncSessionLocal() as db:
                assert (await db.get(User, user_id)).delivers_home is None
        finally:
            async with AsyncSessionLocal() as db:
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
