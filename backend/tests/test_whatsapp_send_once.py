"""Un mensaje de WhatsApp sale y se cobra una sola vez aunque la tarea llegue
repetida: cada copia es dinero en Meta y un riesgo de baneo. Base real; Meta es
falso. Las tareas corren fuera del loop de pytest-asyncio (ver
test_ban_risk_autopause.py)."""
import asyncio
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete

from app.database import AsyncSessionLocal, engine
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.message import Message
from app.models.user import User
from app.workers import tasks

PHONE = "+521234567890"
CASES = [
    ("send_whatsapp", tasks.send_whatsapp_message, ["hola"]),
    ("send_whatsapp_media", tasks.send_whatsapp_voice_note, ["https://x/a.ogg"]),
    ("send_whatsapp_image", tasks.send_whatsapp_image_message, ["https://x/a.png"]),
]


@pytest.fixture
def seeded():
    async def seed():
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            user = User(
                email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test",
                messages_remaining=10,
            )
            db.add(user)
            await db.flush()
            contact = Contact(advertiser_id=user.id, phone=PHONE, name="Cliente", status="active")
            db.add(contact)
            await db.flush()
            msg = Message(
                advertiser_id=user.id, contact_id=contact.id, direction="outbound",
                content="hola", status="queued",
            )
            db.add(msg)
            await db.commit()
            ids = user.id, msg.id
        await engine.dispose()
        return ids

    async def cleanup():
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Message).where(Message.advertiser_id == user_id))
            await db.execute(delete(Campaign).where(Campaign.advertiser_id == user_id))
            await db.execute(delete(Contact).where(Contact.advertiser_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
        await engine.dispose()

    user_id, message_id = asyncio.run(seed())
    yield user_id, message_id
    asyncio.run(cleanup())


def _state(user_id, message_id):
    async def read():
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            remaining = (await db.get(User, user_id)).messages_remaining
            wamid = (await db.get(Message, message_id)).wa_message_id
        await engine.dispose()
        return remaining, wamid
    return asyncio.run(read())


@pytest.mark.parametrize("sender,task,extra", CASES, ids=[c[0] for c in CASES])
def test_second_copy_neither_sends_nor_charges(seeded, sender, task, extra):
    user_id, message_id = seeded
    meta = AsyncMock(return_value=("wamid.1", None))
    with patch(f"app.services.meta_service.{sender}", meta):
        task(str(message_id), PHONE, *extra)
        task(str(message_id), PHONE, *extra)

    assert meta.await_count == 1
    assert _state(user_id, message_id) == (9, "wamid.1")


def test_two_copies_at_once_send_one(seeded):
    """Como el 29-oct: las copias llegan juntas al worker."""
    user_id, message_id = seeded
    calls = []

    async def slow_meta(*args, **kwargs):
        calls.append(1)
        await asyncio.sleep(0.5)  # Mientras, la otra copia ya llegó.
        return f"wamid.{len(calls)}", None

    with patch("app.services.meta_service.send_whatsapp", slow_meta):
        threads = [
            threading.Thread(target=tasks.send_whatsapp_message, args=(str(message_id), PHONE, "hola"))
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
            time.sleep(0.1)
        for thread in threads:
            thread.join(timeout=15)

    assert len(calls) == 1
    assert _state(user_id, message_id) == (9, "wamid.1")


def test_a_failed_send_can_still_retry(seeded):
    """Lo que Meta no aceptó no tiene wamid: el reintento sí debe salir."""
    user_id, message_id = seeded
    meta = AsyncMock(side_effect=[(None, "(#131026) Message undeliverable"), ("wamid.2", None)])
    with patch("app.services.meta_service.send_whatsapp", meta):
        tasks.send_whatsapp_message(str(message_id), PHONE, "hola")
        tasks.send_whatsapp_message(str(message_id), PHONE, "hola")

    assert meta.await_count == 2
    assert _state(user_id, message_id) == (9, "wamid.2")


def _campaign_message(user_id, message_id, campaign_status="running", contact_status="active", until=None):
    async def setup():
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            campaign = Campaign(
                advertiser_id=user_id, name="Promo", type="promo", message_text="hola", status=campaign_status,
            )
            db.add(campaign)
            await db.flush()
            msg = await db.get(Message, message_id)
            msg.campaign_id = campaign.id
            contact = await db.get(Contact, msg.contact_id)
            contact.status = contact_status
            contact.suppressed_until = until
            await db.commit()
        await engine.dispose()
    asyncio.run(setup())


def _message(message_id):
    async def read():
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            msg = await db.get(Message, message_id)
            result = msg.status, msg.error_code
        await engine.dispose()
        return result
    return asyncio.run(read())


FUTURE = datetime.now(timezone.utc) + timedelta(days=30)


@pytest.mark.parametrize("sender,task,extra", CASES, ids=[c[0] for c in CASES])
@pytest.mark.parametrize("setup,reason", [
    ({"campaign_status": "paused"}, "campaign_paused"),
    ({"contact_status": "unsubscribed"}, "contact_not_active"),
    ({"contact_status": "blocked"}, "contact_not_active"),
    ({"until": FUTURE}, "contact_suppressed"),
], ids=["pausada", "baja", "bloqueado", "suprimido"])
def test_a_queued_campaign_message_stops_in_time(seeded, sender, task, extra, setup, reason):
    user_id, message_id = seeded
    _campaign_message(user_id, message_id, **setup)
    meta = AsyncMock(return_value=("wamid.1", None))
    with patch(f"app.services.meta_service.{sender}", meta):
        task(str(message_id), PHONE, *extra)

    assert meta.await_count == 0
    assert _message(message_id) == ("failed", reason)
    assert _state(user_id, message_id) == (10, None)


def test_a_running_campaign_still_sends(seeded):
    user_id, message_id = seeded
    _campaign_message(user_id, message_id)
    meta = AsyncMock(return_value=("wamid.1", None))
    with patch("app.services.meta_service.send_whatsapp", meta):
        tasks.send_whatsapp_message(str(message_id), PHONE, "hola")

    assert meta.await_count == 1


def test_a_completed_campaign_finishes_its_queue(seeded):
    """La campaña se marca terminada antes de que salgan los mensajes con retraso."""
    user_id, message_id = seeded
    _campaign_message(user_id, message_id, campaign_status="completed")
    meta = AsyncMock(return_value=("wamid.1", None))
    with patch("app.services.meta_service.send_whatsapp", meta):
        tasks.send_whatsapp_message(str(message_id), PHONE, "hola")

    assert meta.await_count == 1


def test_a_reply_to_the_contact_is_not_stopped(seeded):
    """charge=False: el cliente contestó y la plantilla ya se cobró."""
    user_id, message_id = seeded
    _campaign_message(user_id, message_id, campaign_status="paused")
    meta = AsyncMock(return_value=("wamid.1", None))
    with patch("app.services.meta_service.send_whatsapp", meta):
        tasks.send_whatsapp_message(str(message_id), PHONE, "hola", charge=False)

    assert meta.await_count == 1


def test_the_owner_can_still_answer_someone_unsubscribed(seeded):
    """Respuesta del dueño desde el Inbox: no es campaña."""
    _user_id, message_id = seeded

    async def unsubscribe():
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            msg = await db.get(Message, message_id)
            (await db.get(Contact, msg.contact_id)).status = "unsubscribed"
            await db.commit()
        await engine.dispose()
    asyncio.run(unsubscribe())

    meta = AsyncMock(return_value=("wamid.1", None))
    with patch("app.services.meta_service.send_whatsapp", meta):
        tasks.send_whatsapp_message(str(message_id), PHONE, "hola")

    assert meta.await_count == 1
