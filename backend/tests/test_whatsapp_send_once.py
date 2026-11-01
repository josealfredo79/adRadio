"""Un mensaje de WhatsApp sale y se cobra una sola vez aunque la tarea llegue
repetida: cada copia es dinero en Meta y un riesgo de baneo. Base real; Meta es
falso. Las tareas corren fuera del loop de pytest-asyncio (ver
test_ban_risk_autopause.py)."""
import asyncio
import threading
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete

from app.database import AsyncSessionLocal, engine
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
