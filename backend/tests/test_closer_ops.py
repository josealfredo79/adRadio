"""send_closer_reminders — nudge único cuando una oferta del Closer está por
vencer, respetando la ventana de 24h; siempre marca reminder_sent_at."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.coupon import Coupon
from app.models.user import User
from app.workers.task_helpers.closer_ops import send_closer_reminders


@pytest.mark.asyncio
async def test_no_due_coupons_is_noop():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    assert await send_closer_reminders(db, datetime.now(timezone.utc)) is None


async def _seed(expires_in_minutes, window_open=True):
    await engine.dispose()
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Spa MX",
                    whatsapp_number="+525599990000")
        db.add(user)
        await db.flush()
        contact = Contact(advertiser_id=user.id, name="Ana Ruiz",
                          phone=f"+52155{uuid.uuid4().hex[:7]}", status="active")
        db.add(contact)
        await db.flush()
        conv = Conversation(advertiser_id=user.id, contact_id=contact.id, status="active",
                            messages=[{"role": "user", "content": "hola"}])
        conv.last_activity = now if window_open else now - timedelta(hours=30)
        db.add(conv)
        coupon = Coupon(
            advertiser_id=user.id, contact_id=contact.id, source="closer",
            code=f"CLO{uuid.uuid4().hex[:6].upper()}", description="Apartado especial",
            expires_at=now + timedelta(minutes=expires_in_minutes),
        )
        db.add(coupon)
        await db.commit()
        return user.id, coupon.id


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Coupon).where(Coupon.advertiser_id == user_id))
        await db.execute(delete(Conversation).where(Conversation.advertiser_id == user_id))
        await db.execute(delete(Contact).where(Contact.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


@pytest.mark.asyncio
async def test_due_coupon_with_open_window_sends_and_marks():
    user_id, coupon_id = await _seed(expires_in_minutes=45, window_open=True)
    try:
        with patch("app.services.meta_service.send_whatsapp", new=AsyncMock(return_value=("s", None))) as mock_send:
            async with AsyncSessionLocal() as db:
                await send_closer_reminders(db, datetime.now(timezone.utc))
                await db.commit()
        mock_send.assert_awaited_once()
        assert "CANJEAR" in mock_send.await_args.args[1]
        async with AsyncSessionLocal() as db:
            assert (await db.get(Coupon, coupon_id)).reminder_sent_at is not None
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_due_coupon_with_closed_window_marks_without_sending():
    user_id, coupon_id = await _seed(expires_in_minutes=45, window_open=False)
    try:
        with patch("app.services.meta_service.send_whatsapp", new=AsyncMock(return_value=("s", None))) as mock_send:
            async with AsyncSessionLocal() as db:
                await send_closer_reminders(db, datetime.now(timezone.utc))
                await db.commit()
        mock_send.assert_not_awaited()
        async with AsyncSessionLocal() as db:
            assert (await db.get(Coupon, coupon_id)).reminder_sent_at is not None
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_coupon_not_yet_in_window_is_left_alone():
    user_id, coupon_id = await _seed(expires_in_minutes=200, window_open=True)
    try:
        with patch("app.services.meta_service.send_whatsapp", new=AsyncMock(return_value=("s", None))) as mock_send:
            async with AsyncSessionLocal() as db:
                await send_closer_reminders(db, datetime.now(timezone.utc))
                await db.commit()
        mock_send.assert_not_awaited()
        async with AsyncSessionLocal() as db:
            assert (await db.get(Coupon, coupon_id)).reminder_sent_at is None
    finally:
        await _cleanup(user_id)
