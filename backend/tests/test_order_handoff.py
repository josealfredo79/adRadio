"""El pedido se entrega al dueño: IaRadio no lo confirma ni manda datos de
pago; el dueño le escribe al cliente con un link wa.me ya escrito
(docs/specs/2026-10-21-pedido-se-entrega-al-dueno.md)."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from urllib.parse import unquote

import pytest
from sqlalchemy import select

from app.api.v1.orders import list_orders
from app.api.v1.portal import ORDER_STATE_LABELS
from app.api.v1.template_seeds import SEED_TEMPLATES
from app.database import AsyncSessionLocal
from app.models.contact import Contact
from app.models.order import Order
from app.models.template import MessageTemplate
from app.models.user import User
from app.services.order_handoff import (
    OLD_SEED_CONFIRMED,
    OLD_SEED_OWNER_NOTIFY,
    customer_wa_link,
)
from app.services.widget_order_service import handle_widget_order
from tests.test_customer_agent import (
    Redis,
    _keys,  # noqa: F401  (fixture autouse: llave falsa de Claude)
    _say,
    fake_claude,
    resp,
    text,
    tool,
    tool_results,
)
from tests.test_customer_agent import _cleanup as _agent_cleanup
from tests.test_customer_agent import _seed as _agent_seed
from tests.test_order_item_whatsapp_integration import _cleanup as _wa_cleanup
from tests.test_order_item_whatsapp_integration import (
    _seed_advertiser_and_contact,
    _seed_product,
    _send_whatsapp,
)
from tests.test_widget_order_service import _cleanup, _seed_contact, _seed_user

CLABE = "BBVA, CLABE 012345678901234567, a nombre de Mary"
LINK = "https://mpago.la/abc"


def _decoded(link: str) -> str:
    return unquote(link.split("?text=", 1)[1])


async def _open(owner_msg: str) -> str:
    """Abre el link corto del aviso al dueño como lo haría su celular: a dónde redirige."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    short = owner_msg.split("👉 Escribirle al cliente: ", 1)[1].split()[0]
    assert "/api/v1/o/" in short and len(short) < 120, short
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/o/" + short.rsplit("/o/", 1)[1])
    assert res.status_code == 302, res.text
    return res.headers["location"]


async def _web_order(user_id, contact_id, pay="Transferencia", address="Calle Hidalgo 5"):
    """Recorre el pedido del chat web; devuelve (respuesta final, mensaje al dueño, kwargs del correo)."""
    async with AsyncSessionLocal() as db:
        user, contact = await db.get(User, user_id), await db.get(Contact, contact_id)
        await handle_widget_order(db, user, contact, "quiero pedir 2 comidas corridas")
    with patch("app.core.email.send_new_order_email", new_callable=AsyncMock) as email, \
            patch("app.services.meta_service.send_whatsapp", new_callable=AsyncMock) as wa:
        steps = ["Juan Pérez"] + ([address] if address else []) + [pay]
        for step in steps:
            async with AsyncSessionLocal() as db:
                user, contact = await db.get(User, user_id), await db.get(Contact, contact_id)
                reply = await handle_widget_order(db, user, contact, step)
        await asyncio.sleep(0.05)
    return reply, (wa.await_args.args[1] if wa.await_args else ""), email.await_args.kwargs


class TestWebChat:
    @pytest.mark.asyncio
    async def test_caso1_caso2_caso3_web_order_is_sent_not_confirmed_and_owner_gets_the_link(self):
        user_id = await _seed_user(business_name="Fonda Doña Mary", delivers_home=True, payment_transfer=CLABE,
                                   whatsapp_number="+525500000001")
        contact_id = await _seed_contact(user_id)
        try:
            reply, owner_msg, email = await _web_order(user_id, contact_id)
            # Caso 1: enviado, nunca confirmado
            assert "Pedido #0001 enviado a Fonda Doña Mary" in reply
            assert "confirmado" not in reply.lower() and "te escriben por whatsapp" in reply.lower()
            # Caso 2: sin datos de pago para el cliente
            assert "CLABE" not in reply and "Datos para transferir" not in reply
            # Caso 3: el dueño recibe el link con el mensaje listo, con los datos de pago
            link = await _open(owner_msg)
            assert link.startswith("https://wa.me/525511112222?text=")
            msg = _decoded(link)
            assert "Fonda Doña Mary" in msg and "#0001" in msg and "Hola Juan" in msg
            assert "Te llega en ___ min." in msg and "A domicilio: Calle Hidalgo 5" in msg and CLABE in msg
            assert email["wa_link"] == link
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_caso3_cash_pickup_link_has_no_payment_data(self):
        user_id = await _seed_user(business_name="Fonda Doña Mary", delivers_home=False, payment_transfer=CLABE,
                                   payment_link=LINK, whatsapp_number="+525500000001")
        contact_id = await _seed_contact(user_id)
        try:
            reply, owner_msg, _ = await _web_order(user_id, contact_id, pay="Efectivo", address=None)
            assert "Para recoger en el local" in reply
            msg = _decoded(await _open(owner_msg))
            assert "Está listo para recoger en ___ min." in msg
            assert CLABE not in msg and LINK not in msg
        finally:
            await _cleanup([user_id])


class TestShortLink:
    @pytest.mark.asyncio
    async def test_bad_or_forged_short_link_is_404(self):
        from httpx import ASGITransport, AsyncClient

        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for token in ("nada", "AAAAAAAAAAAAAAAAAAAAAA.AAAAAAAAAAAAAAAA"):
                assert (await client.get(f"/api/v1/o/{token}")).status_code == 404

    @pytest.mark.asyncio
    async def test_long_order_with_long_transfer_data_still_fits_metas_template_limit(self):
        from app.services.platform_whatsapp import _TEMPLATE_PARAM_MAX, _template_param

        long_transfer = "BBVA Bancomer, CLABE 012345678901234567, cuenta 1234567890, a nombre de María " * 6
        user_id = await _seed_user(business_name="Fonda Doña Mary", delivers_home=True,
                                   payment_transfer=long_transfer[:500], whatsapp_number="+525500000001")
        contact_id = await _seed_contact(user_id)
        try:
            async with AsyncSessionLocal() as db:
                user, contact = await db.get(User, user_id), await db.get(Contact, contact_id)
                await handle_widget_order(db, user, contact, "quiero pedir " + ", ".join(
                    f"{n} órdenes de enchiladas verdes con pollo y crema" for n in range(1, 9)))
            with patch("app.core.email.send_new_order_email", new_callable=AsyncMock), \
                    patch("app.services.meta_service.send_whatsapp", new_callable=AsyncMock) as wa:
                for step in ("Juan Pérez", "Calle Hidalgo 5, Barrio de San Pedro, junto a la tienda", "Transferencia"):
                    async with AsyncSessionLocal() as db:
                        user, contact = await db.get(User, user_id), await db.get(Contact, contact_id)
                        await handle_widget_order(db, user, contact, step)
                owner_msg = wa.await_args.args[1]
            # Con plantilla Meta corta el aviso a 1,024: aunque el aviso creciera de más, el link
            # corto va en la 2.ª línea y sobrevive completo al corte.
            assert owner_msg.index("👉") < 80
            flat = _template_param(owner_msg + "\n" + "x" * 2000)
            assert len(flat) == _TEMPLATE_PARAM_MAX
            assert long_transfer[:60] in _decoded(await _open(flat))
            assert long_transfer[:60] in _decoded(await _open(owner_msg))
        finally:
            await _cleanup([user_id])


class TestLink:
    def test_caso3_total_in_pesos_card_link_and_no_link_without_phone(self):
        owner = User(business_name="Abarrotes Lupe", payment_link=LINK, payment_transfer=CLABE)
        order = Order(order_number=12, items_raw="2 garrafones", customer_name="Ana", delivery_address="Juárez 3",
                      payment_method="Tarjeta")
        msg = _decoded(customer_wa_link(owner, order, "9511234567", 160.0))
        assert "(total aprox. $160)" in msg and f"💳 Paga aquí: {LINK}" in msg and CLABE not in msg
        assert customer_wa_link(owner, order, "+52 951 123 4567").startswith("https://wa.me/529511234567?")
        assert customer_wa_link(owner, order, None) is None
        assert customer_wa_link(owner, order, "web-123") is None


class TestWhatsApp:
    @pytest.mark.asyncio
    async def test_caso1_caso2_caso3_whatsapp_order(self):
        user_id, _ = await _seed_advertiser_and_contact(business_name="Pizzas Toño", delivers_home=True,
                                                        payment_transfer=CLABE, whatsapp_number="+525500000002")
        await _seed_product(user_id, name="Pizza Pepperoni", price=150)
        try:
            async with AsyncSessionLocal() as db:
                advertiser = await db.get(User, user_id)
            for step in ("quiero pedir 2 pizzas de pepperoni", "Sí", "Luis Perez", "Calle Falsa 123"):
                await _send_whatsapp(advertiser, step)
            with patch("app.core.email.send_new_order_email", new_callable=AsyncMock):
                _, send = await _send_whatsapp(advertiser, "Transferencia")
            texts = [c.args[1] for c in send.await_args_list]
            customer = next(t for t in texts if "Pedido #0001" in t)
            owner = next(t for t in texts if "NUEVO PEDIDO" in t)
            assert "enviado a Pizzas Toño" in customer and "confirmado" not in customer.lower()
            assert "total aprox. $300" in customer and "CLABE" not in customer
            msg = _decoded(await _open(owner))
            assert "Hola Luis" in msg and "(total aprox. $300)" in msg and CLABE in msg
            assert "Responde a este número" not in owner
        finally:
            await _wa_cleanup([user_id])

    @pytest.mark.asyncio
    async def test_caso6_untouched_seed_uses_new_text_custom_one_is_filled(self):
        user_id, _ = await _seed_advertiser_and_contact(business_name="Pizzas Toño", delivers_home=True,
                                                        whatsapp_number="+525500000002")
        await _seed_product(user_id, name="Pizza Pepperoni", price=150)
        try:
            async with AsyncSessionLocal() as db:
                db.add_all([
                    MessageTemplate(advertiser_id=user_id, name="Pedido confirmado", category="Pedido",
                                    step="order_confirmed",
                                    content="🍕 {{nombre}}, tu pedido #{{order_number}} ({{items}}) va a {{direccion}}."),
                    MessageTemplate(advertiser_id=user_id, name="Notificar dueño pedido", category="Pedido",
                                    step="order_owner_notify", content=OLD_SEED_OWNER_NOTIFY),
                ])
                await db.commit()
                advertiser = await db.get(User, user_id)
            for step in ("quiero pedir 2 pizzas de pepperoni", "Sí", "Luis Perez", "Calle Falsa 123"):
                await _send_whatsapp(advertiser, step)
            with patch("app.core.email.send_new_order_email", new_callable=AsyncMock):
                _, send = await _send_whatsapp(advertiser, "Efectivo")
            texts = [c.args[1] for c in send.await_args_list]
            customer = next(t for t in texts if "#0001" in t and "NUEVO" not in t)
            owner = next(t for t in texts if "NUEVO PEDIDO" in t)
            assert customer.startswith("🍕 Luis Perez, tu pedido #0001 (")
            assert "{{" not in customer and "va a Calle Falsa 123." in customer
            # La semilla del aviso sin cambios: texto nuevo, siempre con el link.
            assert "{{" not in owner and "Responde a este número" not in owner and "👉 Escribirle al cliente" in owner
        finally:
            await _wa_cleanup([user_id])

    def test_caso6_seeds_are_the_new_texts(self):
        seeds = {t["step"]: t["content"] for t in SEED_TEMPLATES if t.get("step")}
        assert seeds["order_confirmed"] != OLD_SEED_CONFIRMED and "enviado a {{negocio}}" in seeds["order_confirmed"]
        assert "confirmado" not in seeds["order_confirmed"]
        assert "Responde a este número" not in seeds["order_owner_notify"]


class TestAgent:
    @pytest.mark.asyncio
    async def test_caso1_caso2_agent_order_is_sent_with_total_and_no_payment_data(self):
        user_id, ana, pastor, _ = await _agent_seed()
        async with AsyncSessionLocal() as db:
            (await db.get(User, user_id)).payment_transfer = CLABE
            await db.commit()
        r = Redis()
        try:
            claude, _ = fake_claude(
                resp(tool("proponer_pedido", productos=[{"producto_id": str(pastor), "cantidad": 2}],
                          entrega="recoger", pago="Transferencia")),
                resp(text("2 tacos al pastor para recoger, $50. ¿Lo confirmo?"), stop="end_turn"),
            )
            first = await _say(user_id, ana, "mándame 2 de pastor para llevar", r, claude)
            assert first is not None and first.confirm is True, first
            out = await _say(user_id, ana, "Sí, confírmalo", r)
            assert "Pedido #0001 enviado a Tacos El Primo" in out.text and "total aprox. $50" in out.text
            assert "confirmado" not in out.text.lower() and "CLABE" not in out.text
        finally:
            await _agent_cleanup(user_id)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("connected", [False, True])
    async def test_caso5_asking_for_the_order_says_it_is_with_the_business(self, connected):
        user_id, ana, *_ = await _agent_seed()
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            user.phone = "+525599998888"  # número personal del dueño: nunca se da
            if connected:
                user.meta_connection_status, user.meta_display_phone_number = "connected", "+52 951 555 0000"
            db.add(Order(advertiser_id=user_id, contact_id=ana, order_number=3, state="confirmed",
                         items_raw="2 Taco al pastor", confirmed_at=datetime.now(timezone.utc)))
            await db.commit()
        try:
            claude, client = fake_claude(resp(tool("mis_pedidos")),
                                         resp(text("Ya lo tiene el negocio."), stop="end_turn"))
            await _say(user_id, ana, "¿y mi pedido?", Redis(), claude)
            result = tool_results(client)[0]
            assert result["pedidos"][0]["estado"] == "enviado al negocio"
            assert "le escriben por WhatsApp" in result["nota"] and "5599998888" not in result["nota"]
            assert ("+52 951 555 0000" in result["nota"]) is connected
            assert ("avisar_al_dueno" in result["nota"]) is not connected
        finally:
            await _agent_cleanup(user_id)

    def test_caso5_portal_label(self):
        assert ORDER_STATE_LABELS["confirmed"] == "Enviado al negocio"


class TestOrdersPage:
    @pytest.mark.asyncio
    async def test_caso4_list_has_the_customer_link_only_for_sent_orders(self):
        user_id = await _seed_user(business_name="Fonda Doña Mary", payment_transfer=CLABE)
        contact_id = await _seed_contact(user_id)
        try:
            async with AsyncSessionLocal() as db:
                db.add_all([
                    Order(advertiser_id=user_id, contact_id=contact_id, order_number=1, state="confirmed",
                          items_raw="1 comida", customer_name="Ana", payment_method="Transferencia",
                          delivery_address="Hidalgo 5", confirmed_at=datetime.now(timezone.utc)),
                    Order(advertiser_id=user_id, contact_id=contact_id, order_number=2, state="collecting_name",
                          items_raw="1 comida"),
                ])
                await db.commit()
                user = await db.get(User, user_id)
                out = await list_orders(state=None, limit=50, offset=0, current_user=user, db=db)
            by_number = {o["order_number"]: o for o in out["items"]}
            assert by_number[1]["customer_wa_link"].startswith("https://wa.me/525511112222?text=")
            assert CLABE in _decoded(by_number[1]["customer_wa_link"])
            assert by_number[2]["customer_wa_link"] is None
            async with AsyncSessionLocal() as db:
                assert (await db.execute(select(Order).where(Order.advertiser_id == user_id))).scalars().all()
        finally:
            await _cleanup([user_id])

