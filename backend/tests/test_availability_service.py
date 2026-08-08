"""Real-DB tests for availability_service.py — free slots = business_hours
minus existing non-cancelled Appointments."""
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import delete

from app.database import AsyncSessionLocal, engine
from app.models.appointment import Appointment
from app.models.user import User
from app.services.availability_service import TZ, get_available_slots


async def _seed_user(**overrides):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", **overrides)
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Appointment).where(Appointment.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


def _next_monday() -> date:
    today = datetime.now(TZ).date()
    days_ahead = (0 - today.weekday()) % 7
    return today + timedelta(days=days_ahead or 7)


class TestGetAvailableSlots:
    @pytest.mark.asyncio
    async def test_default_hours_used_when_unset(self):
        user_id = await _seed_user()
        try:
            monday = _next_monday()
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                slots = await get_available_slots(db, user, monday)
            assert len(slots) > 0
            assert slots[0].hour == 9
            assert all(s.tzinfo is not None for s in slots)
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_closed_day_returns_no_slots(self):
        user_id = await _seed_user(business_hours={"sun": None})
        try:
            today = datetime.now(TZ).date()
            days_ahead = (6 - today.weekday()) % 7
            sunday = today + timedelta(days=days_ahead or 7)
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                slots = await get_available_slots(db, user, sunday)
            assert slots == []
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_existing_appointment_blocks_its_slot(self):
        user_id = await _seed_user(business_hours={"mon": ["09:00", "11:00"]})
        try:
            monday = _next_monday()
            busy_start = datetime.combine(monday, datetime.min.time(), tzinfo=TZ).replace(hour=9, minute=30)
            async with AsyncSessionLocal() as db:
                db.add(Appointment(
                    advertiser_id=user_id, customer_name="Ocupado", service="X",
                    scheduled_at=busy_start, duration_min=30, status="confirmed",
                ))
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                slots = await get_available_slots(db, user, monday)
            slot_times = {s.strftime("%H:%M") for s in slots}
            assert "09:30" not in slot_times
            assert "09:00" in slot_times  # 30-min slot before the busy one is free
            assert "10:00" in slot_times  # slot right after the busy one is free
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_cancelled_appointment_does_not_block_its_slot(self):
        user_id = await _seed_user(business_hours={"mon": ["09:00", "11:00"]})
        try:
            monday = _next_monday()
            busy_start = datetime.combine(monday, datetime.min.time(), tzinfo=TZ).replace(hour=9, minute=30)
            async with AsyncSessionLocal() as db:
                db.add(Appointment(
                    advertiser_id=user_id, customer_name="Cancelado", service="X",
                    scheduled_at=busy_start, duration_min=30, status="cancelled",
                ))
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                slots = await get_available_slots(db, user, monday)
            slot_times = {s.strftime("%H:%M") for s in slots}
            assert "09:30" in slot_times
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_fully_booked_day_returns_no_slots(self):
        user_id = await _seed_user(business_hours={"mon": ["09:00", "09:30"]})
        try:
            monday = _next_monday()
            busy_start = datetime.combine(monday, datetime.min.time(), tzinfo=TZ).replace(hour=9, minute=0)
            async with AsyncSessionLocal() as db:
                db.add(Appointment(
                    advertiser_id=user_id, customer_name="Ocupado", service="X",
                    scheduled_at=busy_start, duration_min=30, status="pending",
                ))
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                slots = await get_available_slots(db, user, monday)
            assert slots == []
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_past_times_today_are_excluded(self):
        user_id = await _seed_user(business_hours={
            "mon": ["00:00", "23:30"], "tue": ["00:00", "23:30"], "wed": ["00:00", "23:30"],
            "thu": ["00:00", "23:30"], "fri": ["00:00", "23:30"], "sat": ["00:00", "23:30"],
            "sun": ["00:00", "23:30"],
        })
        try:
            today = datetime.now(TZ).date()
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                slots = await get_available_slots(db, user, today)
            now = datetime.now(TZ)
            assert all(s > now for s in slots)
        finally:
            await _cleanup([user_id])
