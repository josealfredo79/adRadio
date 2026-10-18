""""Quiero conectar mi WhatsApp" llega al Inbox de IaRadio
(docs/specs/2026-10-17-meta-sin-friccion.md, casos 2 y 3; real-DB)."""
import uuid

import pytest
from sqlalchemy import delete, select

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.services.meta_help_request import HELP_TAG, request_whatsapp_help


@pytest.fixture
async def seeded(monkeypatch):
    central_pnid = f"pnid-{uuid.uuid4().hex[:10]}"
    monkeypatch.setattr(settings, "IARADIO_WA_PHONE_NUMBER_ID", central_pnid)
    await engine.dispose()
    tail = f"{uuid.uuid4().int % 10**8:08d}"
    async with AsyncSessionLocal() as db:
        central = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="IaRadio",
                       meta_phone_number_id=central_pnid)
        owner = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Tacos El Primo",
                     phone=f"95{tail}")  # 10 dígitos, como lo escribe el dueño
        no_phone = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Sin Teléfono")
        users = [central, owner, no_phone]
        db.add_all(users)
        await db.commit()
        ids = {"central": central.id, "owner": owner.id, "no_phone": no_phone.id}
    yield ids
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for uid in ids.values():
            await db.execute(delete(Message).where(Message.advertiser_id == uid))
            await db.execute(delete(Conversation).where(Conversation.advertiser_id == uid))
            await db.execute(delete(Contact).where(Contact.advertiser_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()
    await engine.dispose()


async def _inbox(db, central_id):
    convs = (await db.execute(select(Conversation).where(Conversation.advertiser_id == central_id))).scalars().all()
    msgs = (await db.execute(select(Message).where(Message.advertiser_id == central_id))).scalars().all()
    return convs, msgs


async def test_caso2_help_request_lands_in_iaradio_inbox_with_bot_paused(seeded):
    async with AsyncSessionLocal() as db:
        owner = await db.get(User, seeded["owner"])
        assert await request_whatsapp_help(db, owner) is True
    async with AsyncSessionLocal() as db:
        convs, msgs = await _inbox(db, seeded["central"])
        contact = (await db.execute(select(Contact).where(Contact.advertiser_id == seeded["central"]))).scalar_one()
    assert len(convs) == 1 and convs[0].status == "escalated" and HELP_TAG in convs[0].tags
    assert contact.name == "Tacos El Primo" and contact.phone.endswith(owner.phone)
    assert len(msgs) == 1 and msgs[0].direction == "inbound" and "Tacos El Primo" in msgs[0].content


async def test_caso3_second_tap_same_day_does_not_duplicate(seeded):
    for _ in range(2):
        async with AsyncSessionLocal() as db:
            owner = await db.get(User, seeded["owner"])
            assert await request_whatsapp_help(db, owner) is True
    async with AsyncSessionLocal() as db:
        convs, msgs = await _inbox(db, seeded["central"])
        contacts = (await db.execute(select(Contact).where(Contact.advertiser_id == seeded["central"]))).scalars().all()
    assert len(convs) == 1 and len(msgs) == 1 and len(contacts) == 1


async def test_owner_without_phone_or_central_account_is_rejected(seeded, monkeypatch):
    async with AsyncSessionLocal() as db:
        assert await request_whatsapp_help(db, await db.get(User, seeded["no_phone"])) is False
        # La cuenta del número central no se pide ayuda a sí misma.
        assert await request_whatsapp_help(db, await db.get(User, seeded["central"])) is False
    monkeypatch.setattr(settings, "IARADIO_WA_PHONE_NUMBER_ID", "")
    async with AsyncSessionLocal() as db:
        assert await request_whatsapp_help(db, await db.get(User, seeded["owner"])) is False
