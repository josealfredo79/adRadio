"""Seguimiento automático de interesados (spec docs/specs/2026-10-15-seguimiento-automatico.md).

Base y Redis reales; el aviso web, Meta y la IA van simulados. Cada prueba
lleva el número de su caso."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import redis.asyncio as aioredis
from sqlalchemy import delete, select

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.services import followup_service as fu
from app.services.owner_alerts import send_morning_digests

# 12:00 en México (UTC-6): de día.
NOON = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)
QUESTION = "¿cuánto cuesta la funda del iPhone 13?"


async def _seed(*, score="warm", hours_ago=20.5, channel="web", **user_kw):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="CityCell", **user_kw)
        db.add(user)
        await db.flush()
        contact = Contact(advertiser_id=user.id, name="Ana López", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        db.add(contact)
        await db.flush()
        asked_at = NOON - timedelta(hours=hours_ago)
        db.add(Conversation(
            advertiser_id=user.id, contact_id=contact.id, lead_score=score, last_activity=asked_at,
            messages=[{"role": "user", "content": QUESTION}, {"role": "assistant", "content": "La funda cuesta $150."}],
        ))
        db.add(Message(advertiser_id=user.id, contact_id=contact.id, direction="inbound", content=QUESTION,
                       status="delivered", channel=channel, created_at=asked_at))
        await db.commit()
        return user.id, contact.id


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for model in (Appointment, Message, Conversation, Contact):
            await db.execute(delete(model).where(model.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await r.delete(f"{fu.PENDING_FOLLOWUP}{user_id}")
    await r.aclose()


class _World:
    """Lo de afuera: avisos web, WhatsApp y la IA."""

    def __init__(self, *, push_contacts=(), push_ok=True, ai="¡Hola Ana! ¿Te aparto la funda del iPhone 13? 🙂"):
        self.push_contacts = set(push_contacts)
        self.push = AsyncMock(return_value=1 if push_ok else 0)
        self.whatsapp = AsyncMock(return_value=("wamid.x", None))
        self.ai = AsyncMock(side_effect=ai) if isinstance(ai, Exception) else AsyncMock(return_value=ai)

    async def run(self, now=NOON):
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            with patch("app.services.web_push.contacts_with_push", AsyncMock(return_value=self.push_contacts)), \
                    patch("app.services.web_push.push_to_contact", self.push), \
                    patch("app.services.meta_service.send_whatsapp", self.whatsapp), \
                    patch("app.services.llm_client.chat_completion", self.ai):
                async with AsyncSessionLocal() as db:
                    return await fu.run_followups(db, r, now)
        finally:
            await r.aclose()


async def _state(contact_id):
    async with AsyncSessionLocal() as db:
        contact = await db.get(Contact, contact_id)
        conv = (await db.execute(select(Conversation).where(Conversation.contact_id == contact_id))).scalar_one()
        outs = (await db.execute(select(Message).where(Message.contact_id == contact_id,
                                                      Message.direction == "outbound"))).scalars().all()
        return contact, conv, outs


@pytest.mark.asyncio
async def test_casos1_2_10_interesado_con_avisos_web_recibe_su_seguimiento_en_el_chat():
    user_id, ana = await _seed()
    try:
        world = _World(push_contacts={ana})
        assert await world.run() == {"web": 1, "whatsapp": 0, "owner": 0}
        # Caso 1: el mensaje habla de lo que preguntó (la IA recibió la plática).
        assert QUESTION in world.ai.await_args.args[0][0]["content"]
        assert world.push.await_args.kwargs["body"] == "¡Hola Ana! ¿Te aparto la funda del iPhone 13? 🙂"
        assert world.push.await_args.kwargs["url"].endswith("?chat=1")
        assert world.whatsapp.await_count == 0
        contact, conv, outs = await _state(ana)
        # Caso 2 y 10: queda en su chat y en el Inbox, así el bot o el agente lo ven si contesta.
        assert conv.messages[-1] == {"role": "assistant", "content": world.push.await_args.kwargs["body"],
                                     "channel": "web"}
        assert [(m.channel, m.status) for m in outs] == [("web", "sent")]
        assert contact.last_followup_at == NOON
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso3_sin_avisos_pero_whatsapp_abierto_llega_por_whatsapp():
    user_id, ana = await _seed(channel=None, hours_ago=21)
    try:
        world = _World()
        assert await world.run() == {"web": 0, "whatsapp": 1, "owner": 0}
        contact, conv, outs = await _state(ana)
        assert world.whatsapp.await_args.args[0] == contact.phone
        assert [(m.channel, m.wa_message_id) for m in outs] == [(None, "wamid.x")]
        assert conv.messages[-1]["role"] == "assistant" and "channel" not in conv.messages[-1]
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("channel,hours_ago", [("web", 22), (None, 30)])
async def test_caso4_sin_canal_gratis_no_se_le_escribe_y_va_al_resumen_del_dueno(channel, hours_ago):
    user_id, ana = await _seed(channel=channel, hours_ago=hours_ago)
    try:
        world = _World()
        assert await world.run() == {"web": 0, "whatsapp": 0, "owner": 1}
        assert world.ai.await_count == 0 and world.whatsapp.await_count == 0
        contact, _, outs = await _state(ana)
        assert outs == [] and contact.last_followup_at == NOON

        sent = AsyncMock(return_value=True)
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            with patch("app.services.owner_alerts._destination", return_value="+525500000000"), \
                    patch("app.services.owner_alerts._send", sent):
                async with AsyncSessionLocal() as db:
                    await send_morning_digests(db, r)
            assert not await r.exists(f"{fu.PENDING_FOLLOWUP}{user_id}")
        finally:
            await r.aclose()
        digest = next(c.args[2] for c in sent.await_args_list if str(c.args[0].id) == str(user_id))
        assert "Preguntó y no compró: Ana López" in digest
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso5_si_ya_agendo_no_se_le_escribe():
    user_id, ana = await _seed()
    async with AsyncSessionLocal() as db:
        db.add(Appointment(advertiser_id=user_id, contact_id=ana, customer_name="Ana", service="Revisión",
                           status="confirmed", scheduled_at=NOON + timedelta(days=2)))
        await db.commit()
    try:
        world = _World(push_contacts={ana})
        assert await world.run() == {"web": 0, "whatsapp": 0, "owner": 0}
        assert (await _state(ana))[0].last_followup_at is None
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso6_platica_fria_no_se_le_escribe():
    user_id, ana = await _seed(score="cold")
    try:
        world = _World(push_contacts={ana})
        assert await world.run() == {"web": 0, "whatsapp": 0, "owner": 0}
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso7_una_vez_por_semana():
    user_id, ana = await _seed()
    try:
        world = _World(push_contacts={ana})
        assert (await world.run())["web"] == 1
        assert (await world.run(NOON + timedelta(minutes=15)))["web"] == 0
        async with AsyncSessionLocal() as db:
            (await db.get(Contact, ana)).last_followup_at = NOON - timedelta(days=3)
            await db.commit()
        assert (await world.run(NOON + timedelta(minutes=30)))["web"] == 0
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso8_de_noche_no_se_manda_y_por_la_web_sale_a_las_9_am():
    user_id, ana = await _seed(hours_ago=20.5)
    try:
        world = _World(push_contacts={ana})
        night = NOON + timedelta(hours=10)  # 22:00 en México
        assert await world.run(night) == {"web": 0, "whatsapp": 0, "owner": 0}
        morning = NOON + timedelta(hours=21)  # 9:00 del día siguiente
        assert (await world.run(morning))["web"] == 1
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("why", ["baja", "bot_pausado", "negocio_en_pausa", "dueno_lo_apago"])
async def test_caso9_no_se_le_escribe(why):
    kw = {}
    if why == "negocio_en_pausa":
        kw = {"subscription_status": "trial", "plan_expires_at": NOON - timedelta(days=1)}
    if why == "dueno_lo_apago":
        kw = {"followup_enabled": False}
    user_id, ana = await _seed(**kw)
    async with AsyncSessionLocal() as db:
        if why == "baja":
            (await db.get(Contact, ana)).status = "unsubscribed"
        if why == "bot_pausado":
            conv = (await db.execute(select(Conversation).where(Conversation.contact_id == ana))).scalar_one()
            conv.status = "escalated"
        await db.commit()
    try:
        world = _World(push_contacts={ana})
        assert await world.run() == {"web": 0, "whatsapp": 0, "owner": 0}
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("ai", [RuntimeError("Groq caído"), "", "x" * 500])
async def test_caso11_si_la_ia_falla_se_manda_el_mensaje_fijo(ai):
    user_id, ana = await _seed()
    try:
        world = _World(push_contacts={ana}, ai=ai)
        assert (await world.run())["web"] == 1
        assert world.push.await_args.kwargs["body"] == (
            "¡Hola, Ana! ¿Pudiste resolver lo que buscabas? Aquí estoy para ayudarte 🙂")
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_si_el_aviso_web_no_llega_cae_a_whatsapp_si_esta_abierto():
    user_id, ana = await _seed(channel=None)
    try:
        world = _World(push_contacts={ana}, push_ok=False)
        assert await world.run() == {"web": 0, "whatsapp": 1, "owner": 0}
    finally:
        await _cleanup(user_id)


@pytest.mark.parametrize("name,first", [("Don Raúl", "Raúl"), ("Sra. Lupita Pérez", "Lupita"), ("+525512345678", ""),
                                        ("Ana López", "Ana"), (None, "")])
def test_nombre_para_saludar(name, first):
    assert fu._first_name(Contact(name=name)) == first
