"""Segundo recordatorio a los 3 días, solo por aviso web
(spec docs/specs/2026-11-10-avisame-y-segundo-recordatorio.md, casos 6-10).

Base real; el aviso web, Meta y la IA van simulados."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.contact import Contact
from app.models.message import Message
from app.models.order import Order
from app.models.user import User
from app.services import followup_service as fu
from tests.test_followup import NOON, QUESTION, _cleanup, _seed, _state


async def _first_sent(contact_id, *, hours_after_question=20.5, asked_hours_ago=74, delivered=True):
    """Como si el primer recordatorio ya hubiera salido (o solo se le hubiera listado al dueño)."""
    async with AsyncSessionLocal() as db:
        contact = await db.get(Contact, contact_id)
        sent_at = NOON - timedelta(hours=asked_hours_ago) + timedelta(hours=hours_after_question)
        contact.last_followup_at = sent_at
        if delivered:
            db.add(Message(advertiser_id=contact.advertiser_id, contact_id=contact_id, direction="outbound",
                           content="¡Hola Ana! ¿Te aparto la funda?", status="sent", sent_at=sent_at, channel="web",
                           created_at=sent_at))
        await db.commit()


class _World:
    def __init__(self, *, push_contacts=(), push_ok=True, ai="¡Hola Ana! ¿Todavía te interesa la funda del iPhone 13? 🙂"):
        self.push_contacts = set(push_contacts)
        self.push = AsyncMock(return_value=1 if push_ok else 0)
        self.whatsapp = AsyncMock(return_value=("wamid.x", None))
        self.ai = AsyncMock(side_effect=ai) if isinstance(ai, Exception) else AsyncMock(return_value=ai)

    async def run(self, now=NOON):
        with patch("app.services.web_push.contacts_with_push", AsyncMock(return_value=self.push_contacts)), \
                patch("app.services.web_push.push_to_contact", self.push), \
                patch("app.services.meta_service.send_whatsapp", self.whatsapp), \
                patch("app.services.llm_client.chat_completion", self.ai):
            async with AsyncSessionLocal() as db:
                return await fu.run_second_followups(db, now)


@pytest.mark.asyncio
async def test_second_followup_after_3_days():
    """Caso 6."""
    user_id, ana = await _seed(hours_ago=74)
    try:
        await _first_sent(ana)
        world = _World(push_contacts={ana})
        assert await world.run() == 1
        # La IA recibe la plática y sabe que es el segundo.
        assert QUESTION in world.ai.await_args.args[0][0]["content"]
        assert "ya le escribiste una vez" in world.ai.await_args.kwargs["system"]
        assert world.push.await_args.kwargs["body"] == "¡Hola Ana! ¿Todavía te interesa la funda del iPhone 13? 🙂"
        contact, conv, outs = await _state(ana)
        assert conv.messages[-1]["channel"] == "web"
        assert [(m.channel, m.status) for m in outs] == [("web", "sent"), ("web", "sent")]
        assert contact.last_followup_at == NOON
        assert world.whatsapp.await_count == 0
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_no_second_when_replied_or_converted():
    """Caso 7: volvió a escribir después del primero, o ya pidió."""
    user_id, ana = await _seed(hours_ago=74)
    try:
        await _first_sent(ana)
        async with AsyncSessionLocal() as db:
            db.add(Message(advertiser_id=user_id, contact_id=ana, direction="inbound", content="gracias",
                           status="delivered", channel="web", created_at=NOON - timedelta(hours=40)))
            await db.commit()
        assert await _World(push_contacts={ana}).run() == 0
    finally:
        await _cleanup(user_id)

    user_id, ana = await _seed(hours_ago=74)
    try:
        await _first_sent(ana)
        async with AsyncSessionLocal() as db:
            db.add(Order(advertiser_id=user_id, contact_id=ana, state="confirmed",
                         created_at=NOON - timedelta(hours=60)))
            await db.commit()
        assert await _World(push_contacts={ana}).run() == 0
    finally:
        async with AsyncSessionLocal() as db:
            for o in (await db.execute(select(Order).where(Order.advertiser_id == user_id))).scalars():
                await db.delete(o)
            await db.commit()
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_second_followup_only_once_and_in_window():
    """Caso 8: una sola vez, de día, con el seguimiento encendido, sin pausa, hasta 4 días."""
    user_id, ana = await _seed(hours_ago=74)
    try:
        await _first_sent(ana)
        world = _World(push_contacts={ana})
        night = datetime(2026, 10, 16, 4, 0, tzinfo=timezone.utc)  # 10 pm en México
        assert await world.run(now=night) == 0
        assert await world.run() == 1
        assert await world.run(now=NOON + timedelta(minutes=15)) == 0  # ya salió
    finally:
        await _cleanup(user_id)

    # Más de 4 días: ya no.
    user_id, ana = await _seed(hours_ago=100)
    try:
        await _first_sent(ana, asked_hours_ago=100)
        assert await _World(push_contacts={ana}).run() == 0
    finally:
        await _cleanup(user_id)

    # Antes de 3 días: todavía no.
    user_id, ana = await _seed(hours_ago=60)
    try:
        await _first_sent(ana, asked_hours_ago=60)
        assert await _World(push_contacts={ana}).run() == 0
    finally:
        await _cleanup(user_id)

    # Dueño con el seguimiento apagado.
    user_id, ana = await _seed(hours_ago=74, followup_enabled=False)
    try:
        await _first_sent(ana)
        assert await _World(push_contacts={ana}).run() == 0
    finally:
        await _cleanup(user_id)

    # El primero solo se le listó al dueño (no le llegó): no hay segundo.
    user_id, ana = await _seed(hours_ago=74)
    try:
        await _first_sent(ana, delivered=False)
        assert await _World(push_contacts={ana}).run() == 0
    finally:
        await _cleanup(user_id)

    # Sin primer recordatorio, no hay segundo.
    user_id, ana = await _seed(hours_ago=74)
    try:
        assert await _World(push_contacts={ana}).run() == 0
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_second_followup_paused_owner():
    """Caso 8: dueño con la pausa puesta."""
    user_id, ana = await _seed(hours_ago=74)
    try:
        await _first_sent(ana)
        with patch("app.services.trial_lifecycle.is_paused", return_value=True):
            assert await _World(push_contacts={ana}).run() == 0
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_second_followup_never_whatsapp():
    """Caso 9: sin avisos web no se le escribe, ni por WhatsApp ni al resumen del dueño."""
    user_id, ana = await _seed(hours_ago=74, channel=None)
    try:
        await _first_sent(ana)
        world = _World(push_contacts=set())
        assert await world.run() == 0
        assert world.whatsapp.await_count == 0
        assert world.ai.await_count == 0
        _contact, _conv, outs = await _state(ana)
        assert len(outs) == 1  # solo el primero
        # Navegador que ya no acepta el aviso: tampoco cae a WhatsApp.
        world = _World(push_contacts={ana}, push_ok=False)
        assert await world.run() == 0
        assert world.whatsapp.await_count == 0
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_second_followup_fallback_and_no_invented_stock():
    """Caso 10: si la IA falla o sale cortado, texto fijo; la IA tiene prohibido decir que sigue disponible."""
    user_id, ana = await _seed(hours_ago=74)
    try:
        await _first_sent(ana)
        world = _World(push_contacts={ana}, ai=RuntimeError("sin IA"))
        assert await world.run() == 1
        assert world.push.await_args.kwargs["body"] == (
            "¡Hola, Ana! ¿Sigues interesado en lo que me preguntaste? Aquí estoy para ayudarte 🙂")
    finally:
        await _cleanup(user_id)

    user_id, ana = await _seed(hours_ago=74)
    try:
        await _first_sent(ana)
        world = _World(push_contacts={ana}, ai="Hola Ana, la funda del iPhone 13 todavía la tenemos y")
        assert await world.run() == 1
        assert world.push.await_args.kwargs["body"].startswith("¡Hola, Ana! ¿Sigues interesado")
        assert "No digas que sigue disponible" in world.ai.await_args.kwargs["system"]
    finally:
        await _cleanup(user_id)


def test_user_model_has_followup_switch():
    assert hasattr(User, "followup_enabled")
