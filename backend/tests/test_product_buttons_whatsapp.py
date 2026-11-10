"""Botones al mostrar un producto en WhatsApp (spec
docs/specs/2026-11-09-botones-producto-whatsapp.md). Base y Redis reales; la IA
y Meta van simulados. Cada prueba lleva el número de su caso."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.core.redis import close_redis
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.user import User
from app.services import product_buttons as pb
from app.services.inbound_pipeline import InboundMessage, process_inbound_message
from app.services.product_link_service import product_url

PHONE = "+525511117777"
R2 = "https://cdn.example.com"
PHOTO = f"{R2}/products/bocina.jpg"


async def _seed(*, contact_name="Juan Pérez", photo=None, **user_kw):
    await engine.dispose()
    await close_redis()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="CityCell", **user_kw)
        db.add(user)
        await db.flush()
        db.add(Contact(advertiser_id=user.id, name=contact_name, phone=PHONE, source="landing"))
        product = Product(advertiser_id=user.id, name="Bocina", price=350, active=True, photo_url=photo)
        db.add(product)
        await db.commit()
        return user.id, product.id


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        order_ids = (await db.execute(select(Order.id).where(Order.advertiser_id == user_id))).scalars().all()
        if order_ids:
            await db.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
        for model in (Order, Product, Message, Conversation, Contact):
            await db.execute(delete(model).where(model.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()
    await close_redis()


class _Phone:
    """El WhatsApp del negocio: texto normal, botones y avisos al dueño."""

    def __init__(self, *, own_number=True, rag="¡Claro! Tenemos la Bocina por $350 🎶"):
        self.send = AsyncMock(side_effect=lambda *a, **k: (f"wamid.{uuid.uuid4()}", None))
        self.owner = AsyncMock(return_value=("wamid.owner", None))
        self.buttons = AsyncMock(side_effect=lambda *a, **k: (f"wamid.{uuid.uuid4()}", None)) if own_number else None
        self.rag = AsyncMock(return_value=rag)

    async def says(self, user_id, text):
        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, user_id)
            with patch("app.services.inbound_pipeline.answer_with_rag", self.rag):
                await process_inbound_message(
                    db, InboundMessage(advertiser=advertiser, from_number=PHONE, body_text=text),
                    send=self.send, send_owner=self.owner, send_buttons=self.buttons)


async def _order(user_id):
    async with AsyncSessionLocal() as db:
        order = (await db.execute(select(Order).where(Order.advertiser_id == user_id)
                                  .order_by(Order.created_at.desc()))).scalars().first()
        items = (await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))).scalars().all() \
            if order else []
        return order, items


async def _show_product(phone, user_id):
    """El cliente pregunta y el bot le muestra la bocina (con botones)."""
    await phone.says(user_id, "¿tienen bocinas?")
    assert phone.buttons.await_count == 1


@pytest.mark.asyncio
async def test_caso1_producto_sale_con_lo_quiero_y_otra_pregunta_y_conserva_el_link():
    user_id, pid = await _seed()
    try:
        phone = _Phone()
        await _show_product(phone, user_id)
        to, body, buttons = phone.buttons.await_args.args
        assert to == PHONE and buttons == [(f"want:{pid}", pb.WANT), ("other", pb.OTHER)]
        assert "Bocina por $350" in body and f"/p/{user_id}/{pid}" in body
        assert phone.send.await_count == 0  # un solo mensaje
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("photo,header", [
    (PHOTO, PHOTO), (None, None), ("/static/x.jpg", None),
    # Foto de fuera de nuestro almacenamiento: Meta podría no poder bajarla y
    # el mensaje no llegaría (revisor-dinero, hallazgo 3).
    ("https://otro-sitio.com/x.jpg", None),
])
async def test_caso2_foto_arriba_solo_si_el_producto_la_tiene(photo, header):
    user_id, _ = await _seed(photo=photo)
    try:
        phone = _Phone()
        with patch("app.services.product_buttons.settings.CF_R2_PUBLIC_URL", R2):
            await _show_product(phone, user_id)
        assert phone.buttons.await_args.kwargs["header_image_url"] == header
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso3_si_meta_rechaza_los_botones_sale_el_texto_con_el_link():
    from app.models.user import User as U
    from app.services import meta_service

    adv = U(id=uuid.uuid4())
    sent = AsyncMock(return_value=("wamid.txt", None))
    with patch.object(meta_service, "_connection", return_value=("123", "tok")), \
            patch.object(meta_service, "graph_request", AsyncMock(side_effect=meta_service.MetaApiError("bad image", status=400))), \
            patch.object(meta_service, "send_whatsapp", sent):
        assert await meta_service.send_whatsapp_reply_buttons(
            PHONE, "Bocina $350 https://x/p/1", pb.PRODUCT_BUTTONS, advertiser=adv, header_image_url=PHOTO,
        ) == ("wamid.txt", None)
        assert sent.await_args.args[1] == "Bocina $350 https://x/p/1"
        # Más de 1024 letras: ni lo intenta con botones.
        sent.reset_mock()
        await meta_service.send_whatsapp_reply_buttons(PHONE, "x" * 1100, pb.PRODUCT_BUTTONS, advertiser=adv)
        assert sent.await_count == 1

    # Y cuando Meta sí lo acepta, la foto va de encabezado del mismo mensaje.
    graph = AsyncMock(return_value={"messages": [{"id": "wamid.ok"}]})
    with patch.object(meta_service, "_connection", return_value=("123", "tok")), \
            patch.object(meta_service, "graph_request", graph):
        await meta_service.send_whatsapp_reply_buttons(PHONE, "Hola", pb.PRODUCT_BUTTONS, advertiser=adv,
                                                       header_image_url=PHOTO)
    interactive = graph.await_args.kwargs["body"]["interactive"]
    assert interactive["header"] == {"type": "image", "image": {"link": PHOTO}}
    assert [b["reply"]["title"] for b in interactive["action"]["buttons"]] == pb.PRODUCT_BUTTONS

    # Meta no contestó (tiempo o conexión): pudo haberlo entregado, así que no
    # se manda el texto otra vez (revisor-dinero, hallazgo 4).
    sent = AsyncMock(return_value=("wamid.txt", None))
    with patch.object(meta_service, "_connection", return_value=("123", "tok")), \
            patch.object(meta_service, "graph_request",
                         AsyncMock(side_effect=meta_service.MetaApiError("timeout", status=0))), \
            patch.object(meta_service, "send_whatsapp", sent):
        sid, err = await meta_service.send_whatsapp_reply_buttons(PHONE, "Hola", pb.PRODUCT_BUTTONS, advertiser=adv)
    assert sid is None and err and sent.await_count == 0


@pytest.mark.asyncio
async def test_caso4a_por_el_numero_central_no_salen_botones():
    user_id, _ = await _seed()
    try:
        phone = _Phone(own_number=False)
        await phone.says(user_id, "¿tienen bocinas?")
        assert "/p/" in phone.send.await_args.args[1]  # el link de siempre
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso4b_si_el_bot_le_paso_la_pregunta_al_dueno_no_salen_botones():
    user_id, _ = await _seed(phone="+525500000001")
    try:
        phone = _Phone(rag="[[PREGUNTAR_AL_DUENO]] ¿La bocina es bluetooth?")
        with patch("app.services.inbound_pipeline.platform_enabled", return_value=True), \
                patch("app.services.inbound_pipeline.escalate_to_owner",
                      AsyncMock(return_value="Déjame confirmarlo con el equipo 🙏")):
            await phone.says(user_id, "¿la bocina es bluetooth?")
        assert phone.buttons.await_count == 0
        assert phone.send.await_args.args[1].startswith("Déjame confirmarlo")
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso4c_platica_en_pausa_no_contesta_nada():
    user_id, _ = await _seed()
    try:
        phone = _Phone()
        await _show_product(phone, user_id)
        async with AsyncSessionLocal() as db:
            conv = (await db.execute(select(Conversation).where(Conversation.advertiser_id == user_id))).scalar_one()
            conv.status = "escalated"
            await db.commit()
        await phone.says(user_id, "¿y la bocina tiene garantía?")
        assert phone.buttons.await_count == 1 and phone.send.await_count == 0
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_casos5_6_lo_quiero_arranca_el_pedido_y_ofrece_su_nombre():
    user_id, pid = await _seed()
    try:
        phone = _Phone()
        await _show_product(phone, user_id)
        await phone.says(user_id, pb.WANT)
        _, body, buttons = phone.buttons.await_args.args
        assert "Bocina" in body and "$350" in body and "nombre" in body
        assert "¿Te gustaría hacer un pedido" not in body
        assert buttons == ["✅ Juan Pérez"]
        order, items = await _order(user_id)
        assert order.state == "collecting_name" and order.items_raw == "Bocina"
        assert [(i.product_id, i.quantity) for i in items] == [(pid, 1)]
        # Caso 6: tocar su nombre guarda el nombre sin el dibujito.
        await phone.says(user_id, "✅ Juan Pérez")
        order, _ = await _order(user_id)
        assert order.customer_name == "Juan Pérez"
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso6_sin_nombre_en_whatsapp_no_hay_boton_y_puede_escribirlo():
    user_id, _ = await _seed(contact_name="+525511117777")
    try:
        phone = _Phone()
        await _show_product(phone, user_id)
        await phone.says(user_id, pb.WANT)
        assert phone.buttons.await_count == 1  # el nombre se pide como texto
        assert "nombre" in phone.send.await_args.args[1]
        await phone.says(user_id, "Marta Ruiz")
        order, _ = await _order(user_id)
        assert order.customer_name == "Marta Ruiz"
    finally:
        await _cleanup(user_id)


async def _to_delivery(phone, user_id):
    await _show_product(phone, user_id)
    await phone.says(user_id, pb.WANT)
    await phone.says(user_id, "✅ Juan Pérez")


@pytest.mark.asyncio
async def test_caso7_con_domicilio_pregunta_entrega_y_a_domicilio_pide_direccion():
    user_id, _ = await _seed(delivers_home=True)
    try:
        phone = _Phone()
        await _to_delivery(phone, user_id)
        assert phone.buttons.await_args.args[2] == pb.DELIVERY_BUTTONS
        await phone.says(user_id, pb.HOME)
        assert "dirección" in phone.send.await_args.args[1]
        await phone.says(user_id, "Calle Hidalgo 12, Centro")
        assert phone.buttons.await_args.args[2] == pb.PAYMENT_BUTTONS
        order, _ = await _order(user_id)
        assert order.state == "collecting_payment" and order.delivery_address == "Calle Hidalgo 12, Centro"
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso7_recojo_en_tienda_salta_al_pago():
    user_id, _ = await _seed(delivers_home=True)
    try:
        phone = _Phone()
        await _to_delivery(phone, user_id)
        await phone.says(user_id, pb.PICKUP)
        assert phone.buttons.await_args.args[2] == pb.PAYMENT_BUTTONS
        assert "recoger" in phone.buttons.await_args.args[1]
        order, _ = await _order(user_id)
        assert order.state == "collecting_payment" and order.delivery_address is None
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso7_sin_domicilio_no_se_pregunta_entrega():
    user_id, _ = await _seed(delivers_home=None)
    try:
        phone = _Phone()
        await _to_delivery(phone, user_id)
        _, body, buttons = phone.buttons.await_args.args
        assert buttons == pb.PAYMENT_BUTTONS and "recoger" in body
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso8_pago_con_botones_cierra_el_pedido_y_avisa_al_dueno():
    user_id, _ = await _seed(delivers_home=True, phone="+525500000001")
    try:
        phone = _Phone()
        await _to_delivery(phone, user_id)
        await phone.says(user_id, pb.PICKUP)
        await phone.says(user_id, "💵 Efectivo")
        order, _ = await _order(user_id)
        assert order.state == "confirmed" and order.payment_method == "Efectivo"
        owner = next(c.args[1] for c in phone.owner.await_args_list if "NUEVO PEDIDO" in c.args[1])
        assert "Bocina · total aprox. $350" in owner  # el dueño ve el total, como el cliente
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso9_otra_pregunta_invita_a_preguntar_sin_ia_ni_pedido():
    user_id, _ = await _seed()
    try:
        phone = _Phone()
        await _show_product(phone, user_id)
        rag_calls = phone.rag.await_count
        await phone.says(user_id, pb.OTHER)
        assert phone.send.await_args.args[1] == pb.OTHER_REPLY
        assert phone.rag.await_count == rag_calls
        order, _ = await _order(user_id)
        assert order is None
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso10_producto_dado_de_baja_no_crea_pedido():
    user_id, pid = await _seed()
    try:
        phone = _Phone()
        await _show_product(phone, user_id)
        async with AsyncSessionLocal() as db:
            (await db.get(Product, pid)).active = False
            await db.commit()
        await phone.says(user_id, pb.WANT)
        assert phone.send.await_args.args[1] == pb.GONE_REPLY
        order, _ = await _order(user_id)
        assert order is None
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso11_lo_quiero_con_pedido_a_medias_empieza_uno_nuevo():
    user_id, _ = await _seed()
    try:
        phone = _Phone()
        await _show_product(phone, user_id)
        await phone.says(user_id, pb.WANT)
        first, _ = await _order(user_id)
        await phone.says(user_id, pb.WANT)  # lo vuelve a tocar en vez de dar su nombre
        async with AsyncSessionLocal() as db:
            orders = (await db.execute(select(Order).where(Order.advertiser_id == user_id)
                                       .order_by(Order.created_at))).scalars().all()
        assert [o.state for o in orders] == ["cancelled", "collecting_name"]
        assert orders[0].id == first.id and all(o.customer_name is None for o in orders)
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso12_pedido_escrito_tambien_lleva_botones():
    user_id, _ = await _seed(delivers_home=True)
    try:
        phone = _Phone()
        await phone.says(user_id, "quiero pedir una bocina")
        assert phone.buttons.await_args.args[2] == pb.CONFIRM_BUTTONS
        await phone.says(user_id, "✅ Sí")
        assert phone.buttons.await_args.args[2] == ["✅ Juan Pérez"]
        await phone.says(user_id, "Juan")
        assert phone.buttons.await_args.args[2] == pb.DELIVERY_BUTTONS
        # Escribe la dirección de una vez en vez de tocar: también sirve.
        await phone.says(user_id, "Calle Hidalgo 12")
        order, _ = await _order(user_id)
        assert order.state == "collecting_payment" and order.delivery_address == "Calle Hidalgo 12"
    finally:
        await _cleanup(user_id)


def test_helpers():
    assert pb.plain("💵 Efectivo") == "Efectivo" and pb.plain("¿Qué?") == "¿Qué?"
    assert pb.is_tap("lo quiero", pb.WANT) and not pb.is_tap("lo quiero ya", pb.WANT)
    assert pb.is_button_tap("🛒 Lo quiero", pb.WANT) and not pb.is_button_tap("lo quiero", pb.WANT)
    assert pb.delivery_choice("paso por él") == "pickup" and pb.delivery_choice("Av. Juárez 3") is None
    assert pb.name_buttons(Contact(name="Maximiliano Hernández López")) == ["✅ Maximiliano Hernán"]
    assert pb.name_buttons(Contact(name="")) == []
    assert product_url(Product(id=uuid.uuid4(), advertiser_id=uuid.uuid4())).count("/p/") == 1


@pytest.mark.asyncio
async def test_lo_quiero_pide_el_producto_del_boton_aunque_despues_se_hablo_de_otro():
    """revisor-dinero, hallazgo 1: el botón de la bocina, tocado después de
    que salió el link de otro producto, sigue pidiendo la bocina."""
    user_id, bocina = await _seed()
    try:
        async with AsyncSessionLocal() as db:
            audif = Product(advertiser_id=user_id, name="Audífonos", price=150, active=True)
            db.add(audif)
            await db.commit()
            audif_id = audif.id
        phone = _Phone()
        await _show_product(phone, user_id)
        phone.rag.return_value = "Los Audífonos cuestan $150 🎧"
        await phone.says(user_id, "¿y audífonos?")
        assert phone.buttons.await_args.args[2][0] == (f"want:{audif_id}", pb.WANT)
        await phone.says(user_id, f"want:{bocina}")  # toca el botón de la bocina
        order, items = await _order(user_id)
        assert order.items_raw == "Bocina" and [i.product_id for i in items] == [bocina]
        async with AsyncSessionLocal() as db:
            inbound = (await db.execute(select(Message).where(
                Message.advertiser_id == user_id, Message.direction == "inbound"
            ).order_by(Message.created_at.desc()))).scalars().first()
        assert inbound.content == pb.WANT  # en el Inbox se ve el botón, no el id
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["plan_pending_confirmation", "plan_confirmed"])
async def test_lo_quiero_no_cancela_la_compra_de_un_plan(state):
    """revisor-dinero, hallazgo 2."""
    user_id, bocina = await _seed()
    try:
        async with AsyncSessionLocal() as db:
            contact = (await db.execute(select(Contact).where(Contact.advertiser_id == user_id))).scalar_one()
            db.add(Order(advertiser_id=user_id, contact_id=contact.id, items_raw="Plan Negocio",
                         state=state, order_number=1))
            await db.commit()
        phone = _Phone()
        await phone.says(user_id, f"want:{bocina}")
        async with AsyncSessionLocal() as db:
            states = {o.items_raw: o.state for o in (await db.execute(
                select(Order).where(Order.advertiser_id == user_id))).scalars()}
        assert states == {"Plan Negocio": state, "Bocina": "collecting_name"}
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_tocar_lo_quiero_no_canjea_un_cupon_activo():
    from datetime import datetime, timedelta, timezone

    from app.models.coupon import Coupon

    user_id, bocina = await _seed()
    try:
        async with AsyncSessionLocal() as db:
            contact = (await db.execute(select(Contact).where(Contact.advertiser_id == user_id))).scalar_one()
            db.add(Coupon(advertiser_id=user_id, contact_id=contact.id, code=f"T{uuid.uuid4().hex[:8]}", discount_value=10,
                          expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
            await db.commit()
        phone = _Phone()
        await phone.says(user_id, f"want:{bocina}")
        async with AsyncSessionLocal() as db:
            coupon = (await db.execute(select(Coupon).where(Coupon.advertiser_id == user_id))).scalar_one()
            assert coupon.redeemed_at is None and coupon.used_count == 0
            await db.delete(coupon)
            await db.commit()
        order, _ = await _order(user_id)
        assert order.items_raw == "Bocina"
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_el_mismo_toque_dos_veces_no_crea_dos_pedidos():
    user_id, bocina = await _seed()
    try:
        phone = _Phone()
        for _ in range(2):  # Meta reenvía el mismo webhook
            async with AsyncSessionLocal() as db:
                advertiser = await db.get(User, user_id)
                await process_inbound_message(
                    db, InboundMessage(advertiser=advertiser, from_number=PHONE, body_text=f"want:{bocina}",
                                       external_message_id="wamid.same-tap"),
                    send=phone.send, send_owner=phone.owner, send_buttons=phone.buttons)
        async with AsyncSessionLocal() as db:
            orders = (await db.execute(select(Order).where(Order.advertiser_id == user_id))).scalars().all()
        assert len(orders) == 1
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_tocar_su_nombre_guarda_el_nombre_completo_aunque_el_boton_lo_corte():
    """Prueba local 2026-11-09: "Jose Alfredo Roman Cruz" quedaba "Jose Alfredo Roman"."""
    user_id, bocina = await _seed(contact_name="Jose Alfredo Roman Cruz")
    try:
        phone = _Phone()
        await phone.says(user_id, f"want:{bocina}")
        assert phone.buttons.await_args.args[2] == ["✅ Jose Alfredo Roman"]
        await phone.says(user_id, "✅ Jose Alfredo Roman")
        order, _ = await _order(user_id)
        assert order.customer_name == "Jose Alfredo Roman Cruz"
    finally:
        await _cleanup(user_id)
