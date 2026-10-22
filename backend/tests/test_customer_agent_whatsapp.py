"""Agente del cliente en WhatsApp (spec docs/specs/2026-10-15-agente-en-whatsapp.md).

Entrada real de WhatsApp (process_inbound_message) con base y Redis reales;
solo Claude y Meta van simulados. Cada prueba lleva el número de su caso."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.config import settings
from app.core.redis import close_redis
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
from app.services.inbound_pipeline import InboundMessage, process_inbound_message
from tests.test_customer_agent import _next_open_day, fake_claude, resp, text, tool

PHONE = "+525512340000"
OTHER_PHONE = "+525512349999"


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "CUSTOMER_AGENT_WHATSAPP", "all")
    monkeypatch.setattr("app.services.plan_usage.register_bot_conversation", AsyncMock())


async def _seed():
    await engine.dispose()
    await close_redis()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Barbería Toño",
                    customer_agent_enabled=True)
        db.add(user)
        await db.flush()
        ana = Contact(advertiser_id=user.id, name="Ana López", phone=PHONE, source="landing")
        beto = Contact(advertiser_id=user.id, name="Beto", phone=OTHER_PHONE, source="landing")
        corte = Product(advertiser_id=user.id, name="Cera para cabello", price=80, active=True)
        db.add_all([ana, beto, corte])
        await db.commit()
        return user.id, ana.id, beto.id, corte.id


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
    await close_redis()


class _Sent:
    def __init__(self):
        self.text = AsyncMock(return_value=(f"wamid.{uuid.uuid4().hex}", None))
        self.buttons = AsyncMock(return_value=(f"wamid.{uuid.uuid4().hex}", None))
        self.owner_appt = AsyncMock()
        self.owner_order = AsyncMock()
        self.owner_text = AsyncMock()

    def last(self) -> str:
        calls = self.text.await_args_list + self.buttons.await_args_list
        return calls[-1].args[1] if calls else ""


async def _wa(user_id, body, claude=None, *, phone=PHONE, buttons=True) -> _Sent:
    sent = _Sent()
    async with AsyncSessionLocal() as db:
        advertiser = await db.get(User, user_id)
        msg = InboundMessage(advertiser=advertiser, from_number=phone, body_text=body,
                             external_message_id=f"wamid.in.{uuid.uuid4().hex}")
        with patch("app.services.appointment_booking_service._notify_owner", sent.owner_appt), \
                patch("app.services.widget_order_service._notify_owner", sent.owner_order), \
                patch("app.services.customer_agent._owner_text", sent.owner_text), \
                patch("app.core.email.send_new_appointment_email", AsyncMock()):
            kwargs = {"send": sent.text, "send_owner": sent.text, "send_buttons": sent.buttons if buttons else None}
            if claude:
                with claude:
                    await process_inbound_message(db, msg, **kwargs)
            else:
                await process_inbound_message(db, msg, **kwargs)
    return sent


async def _contact(contact_id) -> Contact:
    async with AsyncSessionLocal() as db:
        return await db.get(Contact, contact_id)


def _booking_claude(when):
    return fake_claude(
        resp(tool("horarios_libres", fecha=when.date().isoformat())),
        resp(tool("proponer_cita", servicio="Corte", fecha_hora=when.strftime("%Y-%m-%dT%H:%M"))),
        resp(text("Tengo a las 5 pm para tu corte. ¿Lo confirmo?"), stop="end_turn"),
    )


@pytest.mark.asyncio
async def test_caso1_apagado_contesta_como_hoy(monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_AGENT_WHATSAPP", "")
    user_id, *_ = await _seed()
    try:
        claude, client = fake_claude()
        sent = await _wa(user_id, "quiero agendar una cita mañana", claude)
        assert client.messages.create.await_count == 0
        assert sent.buttons.await_count == 0 and sent.text.await_count == 1  # flujo fijo de citas
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso1_solo_los_correos_del_interruptor(monkeypatch):
    user_id, *_ = await _seed()
    try:
        async with AsyncSessionLocal() as db:
            email = (await db.get(User, user_id)).email
        monkeypatch.setattr(settings, "CUSTOMER_AGENT_WHATSAPP", "otro@negocio.com")
        claude, client = fake_claude()
        await _wa(user_id, "quiero agendar una cita mañana", claude)
        assert client.messages.create.await_count == 0
        monkeypatch.setattr(settings, "CUSTOMER_AGENT_WHATSAPP", f"otro@negocio.com, {email.upper()}")
        claude, _ = _booking_claude(_next_open_day())
        sent = await _wa(user_id, "quiero agendar una cita mañana", claude)
        assert sent.buttons.await_count == 1
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_casos2_3_12_cita_con_botones_aviso_por_whatsapp_y_queda_en_el_inbox():
    user_id, ana, *_ = await _seed()
    when = _next_open_day()
    try:
        claude, _ = _booking_claude(when)
        sent = await _wa(user_id, "quiero una cita mañana en la tarde", claude)
        # Caso 2: pregunta con botones Sí / No, todavía sin cita.
        assert sent.buttons.await_args.args[2] == agent.CONFIRM_BUTTONS
        assert sent.buttons.await_args.args[1].endswith("¿Lo confirmo?")
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(Appointment).where(Appointment.contact_id == ana))).first() is None

        # Caso 3: el botón llega como su título.
        sent = await _wa(user_id, "Sí, confírmalo")
        assert sent.last().startswith("✅ ¡Listo! Tu cita de Corte")
        async with AsyncSessionLocal() as db:
            appt = (await db.execute(select(Appointment).where(Appointment.contact_id == ana))).scalar_one()
            conv = (await db.execute(select(Conversation).where(Conversation.contact_id == ana))).scalar_one()
        assert appt.scheduled_at.astimezone(TZ) == when and appt.status == "confirmed"
        assert sent.owner_appt.await_args.args[2] == "whatsapp"  # "desde WhatsApp", no "desde tu página web"
        # Caso 12: las dos vueltas quedan en la plática del Inbox.
        said = [m["content"] for m in conv.messages]
        assert "quiero una cita mañana en la tarde" in said and "Sí, confírmalo" in said
        assert any(c.startswith("✅ ¡Listo!") for c in said)
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso4_boton_no_no_crea_nada():
    user_id, ana, *_ = await _seed()
    try:
        claude, _ = _booking_claude(_next_open_day())
        await _wa(user_id, "quiero una cita mañana en la tarde", claude)
        sent = await _wa(user_id, "No")
        assert "no lo hago" in sent.last().lower()
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(Appointment).where(Appointment.contact_id == ana))).first() is None
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso5_pedido_por_whatsapp_avisa_al_dueno_con_el_canal():
    user_id, ana, _, corte = await _seed()
    try:
        claude, _ = fake_claude(
            resp(tool("buscar_productos", texto="cera")),
            resp(tool("proponer_pedido", productos=[{"producto_id": str(corte), "cantidad": 1}],
                      entrega="recoger", pago="Efectivo")),
            resp(text("1 Cera para recoger, $80. ¿Lo confirmo?"), stop="end_turn"),
        )
        sent = await _wa(user_id, "quiero pedir una cera para recoger", claude)
        assert sent.buttons.await_count == 1
        sent = await _wa(user_id, "Sí, confírmalo")
        assert "Pedido #0001 enviado a" in sent.last()
        assert sent.owner_order.await_args.kwargs["origin"] == "por WhatsApp"
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(Order).where(Order.contact_id == ana))).scalar_one().state == "confirmed"
    finally:
        await _cleanup(user_id)


async def _future_appointment(user_id, contact_id, **extra):
    async with AsyncSessionLocal() as db:
        appt = Appointment(advertiser_id=user_id, contact_id=contact_id, customer_name="Ana López",
                           customer_phone=PHONE, service="Corte", status="confirmed",
                           scheduled_at=datetime.now(timezone.utc) + timedelta(days=5), **extra)
        db.add(appt)
        await db.commit()
        return appt.id


@pytest.mark.asyncio
async def test_caso6_cancelar_a_secas_con_cita_va_al_agente_y_no_da_de_baja():
    user_id, ana, *_ = await _seed()
    appt_id = await _future_appointment(user_id, ana)
    try:
        claude, client = fake_claude(
            resp(tool("mis_citas")),
            resp(tool("proponer_cancelar_cita", cita_id=str(appt_id))),
            resp(text("¿Cancelo tu cita de Corte? ¿Lo confirmo?"), stop="end_turn"),
        )
        sent = await _wa(user_id, "Cancelar", claude)
        assert client.messages.create.await_count == 3 and sent.buttons.await_count == 1
        assert (await _contact(ana)).status == "active"
        sent = await _wa(user_id, "Sí, confírmalo")
        async with AsyncSessionLocal() as db:
            assert (await db.get(Appointment, appt_id)).status == "cancelled"
        assert "por WhatsApp" in sent.owner_text.await_args.args[1]
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso7_cancelar_a_secas_sin_nada_explica_como_darse_de_baja():
    user_id, ana, *_ = await _seed()
    try:
        claude, client = fake_claude()
        sent = await _wa(user_id, "cancelar", claude)
        assert sent.last() == agent.NOTHING_TO_CANCEL_REPLY
        assert client.messages.create.await_count == 0
        assert (await _contact(ana)).status == "active"
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("word", ["baja", "STOP", "salir", "no quiero"])
async def test_caso8_las_demas_palabras_siguen_dando_de_baja(word):
    user_id, ana, *_ = await _seed()
    try:
        await _wa(user_id, word)
        assert (await _contact(ana)).status == "unsubscribed"
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso9_el_si_es_del_agente_aunque_haya_un_recordatorio_esperando():
    user_id, ana, *_ = await _seed()
    reminder_id = await _future_appointment(user_id, ana, awaiting_confirmation=True)
    when = _next_open_day()
    try:
        claude, _ = _booking_claude(when)
        await _wa(user_id, "quiero otra cita mañana en la tarde", claude)
        await _wa(user_id, "si")
        async with AsyncSessionLocal() as db:
            appts = (await db.execute(select(Appointment).where(Appointment.contact_id == ana))).scalars().all()
            reminder = await db.get(Appointment, reminder_id)
        assert len(appts) == 2  # la cita nueva del agente sí se creó
        assert reminder.awaiting_confirmation is True  # el recordatorio no se tocó
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso10_el_si_al_recordatorio_solo_confirma_la_cita_de_ese_cliente(monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_AGENT_WHATSAPP", "")
    user_id, _, beto, _ = await _seed()
    async with AsyncSessionLocal() as db:
        beto_appt = Appointment(advertiser_id=user_id, contact_id=beto, customer_name="Beto",
                                customer_phone=OTHER_PHONE, service="Corte", status="pending",
                                awaiting_confirmation=True,
                                scheduled_at=datetime.now(timezone.utc) + timedelta(days=1))
        db.add(beto_appt)
        await db.commit()
        beto_id = beto_appt.id
    try:
        await _wa(user_id, "si")  # Ana no tiene recordatorio pendiente
        async with AsyncSessionLocal() as db:
            appt = await db.get(Appointment, beto_id)
        assert appt.awaiting_confirmation is True and appt.status == "pending"
        await _wa(user_id, "si", phone=OTHER_PHONE)
        async with AsyncSessionLocal() as db:
            appt = await db.get(Appointment, beto_id)
        assert appt.status == "confirmed"
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso11_si_claude_falla_contestan_los_flujos_fijos():
    user_id, *_ = await _seed()
    try:
        claude, client = fake_claude()
        client.messages.create.side_effect = RuntimeError("Claude caído")
        sent = await _wa(user_id, "quiero agendar una cita mañana", claude)
        assert client.messages.create.await_count == 1
        assert sent.buttons.await_count == 0 and sent.text.await_count == 1
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso13_bot_pausado_el_agente_no_se_mete():
    user_id, ana, *_ = await _seed()
    async with AsyncSessionLocal() as db:
        db.add(Conversation(advertiser_id=user_id, contact_id=ana, messages=[], status="escalated"))
        await db.commit()
    try:
        claude, client = fake_claude()
        sent = await _wa(user_id, "quiero una cita mañana", claude)
        assert client.messages.create.await_count == 0
        assert sent.text.await_count == 0 and sent.buttons.await_count == 0
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_numero_central_sin_botones_no_usa_el_agente():
    user_id, *_ = await _seed()
    try:
        claude, client = fake_claude()
        await _wa(user_id, "quiero agendar una cita mañana", claude, buttons=False)
        assert client.messages.create.await_count == 0
    finally:
        await _cleanup(user_id)
