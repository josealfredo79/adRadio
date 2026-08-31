"""Pricing: a send to a closed-window contact bills 1 message to the
advertiser's quota at the moment the reopen template goes out (in
_offer_or_queue), and the deferred content fired later on the contact's
reply carries `charge=False` so it isn't billed a second time.

Real-DB style (each Celery send task runs its own asyncio.run() internally).
"""
import asyncio
import uuid
from unittest.mock import patch

from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.message import Message
from app.models.user import User
from app.workers.tasks import send_whatsapp_voice_note


def _seed(messages_remaining: int):
    async def _s():
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            adv = User(
                email=f"{uuid.uuid4()}@test.com", password_hash="x",
                business_name="Test", messages_remaining=messages_remaining,
            )
            db.add(adv)
            await db.flush()
            contact = Contact(advertiser_id=adv.id, phone="+521234567890", name="C", status="active")
            db.add(contact)
            await db.flush()
            msg = Message(
                advertiser_id=adv.id, contact_id=contact.id, direction="outbound",
                content="[AUDIO] https://x/a.ogg", status="queued",
            )
            db.add(msg)
            await db.commit()
            return adv.id, msg.id
    return asyncio.run(_s())


def _remaining(adv_id):
    async def _c():
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            adv = await db.get(User, adv_id)
            r = adv.messages_remaining
        await engine.dispose()
        return r
    return asyncio.run(_c())


def test_default_charge_decrements_quota():
    adv_id, msg_id = _seed(5)
    sid = f"sid.{uuid.uuid4().hex[:12]}"
    with patch("app.services.meta_service.send_whatsapp_media", return_value=(sid, None)):
        send_whatsapp_voice_note(str(msg_id), "+521234567890", "https://x/a.ogg", "")
    assert _remaining(adv_id) == 4


def test_charge_false_does_not_decrement_quota():
    adv_id, msg_id = _seed(5)
    sid = f"sid.{uuid.uuid4().hex[:12]}"
    with patch("app.services.meta_service.send_whatsapp_media", return_value=(sid, None)):
        send_whatsapp_voice_note(str(msg_id), "+521234567890", "https://x/a.ogg", "", charge=False)
    assert _remaining(adv_id) == 5


def test_charge_false_delivers_even_at_zero_quota():
    """The advertiser already paid upfront for the reopen template — a
    balance that has since hit zero must not block the deferred content."""
    adv_id, msg_id = _seed(0)
    sid = f"sid.{uuid.uuid4().hex[:12]}"
    with patch("app.services.meta_service.send_whatsapp_media", return_value=(sid, None)):
        send_whatsapp_voice_note(str(msg_id), "+521234567890", "https://x/a.ogg", "", charge=False)

    async def _status():
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            m = await db.get(Message, msg_id)
            s = m.status, m.error_code
        await engine.dispose()
        return s
    status, err = asyncio.run(_status())
    assert status == "sent"
    assert err is None
