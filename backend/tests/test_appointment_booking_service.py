"""Tests for appointment_booking_service.py — the Spanish date parser
(pure function) and the shared booking state machine (real DB + fake Redis),
independent of both WhatsApp's and the widget's own plumbing."""
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal, engine
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.user import User
from app.services.appointment_booking_service import (
    NEEDS_CONTACT_REPLY,
    format_spanish_date,
    handle_appointment_booking,
    parse_spanish_date,
)


class TestParseSpanishDate:
    def test_hoy(self):
        today = date(2026, 8, 10)
        assert parse_spanish_date("hoy", today=today) == today

    def test_manana(self):
        today = date(2026, 8, 10)
        assert parse_spanish_date("mañana", today=today) == today + timedelta(days=1)
        assert parse_spanish_date("manana", today=today) == today + timedelta(days=1)

    def test_pasado_manana(self):
        today = date(2026, 8, 10)
        assert parse_spanish_date("pasado mañana", today=today) == today + timedelta(days=2)

    def test_weekday_name_returns_next_occurrence(self):
        # 2026-08-10 is a Monday
        today = date(2026, 8, 10)
        assert parse_spanish_date("el viernes", today=today) == date(2026, 8, 14)
        # Asking for "lunes" on a Monday means NEXT Monday, not today
        assert parse_spanish_date("el lunes", today=today) == date(2026, 8, 17)

    def test_day_of_month_name(self):
        today = date(2026, 8, 10)
        assert parse_spanish_date("15 de agosto", today=today) == date(2026, 8, 15)

    def test_day_of_month_name_rolls_to_next_year_if_past(self):
        today = date(2026, 8, 10)
        assert parse_spanish_date("5 de enero", today=today) == date(2027, 1, 5)

    def test_numeric_date(self):
        today = date(2026, 8, 10)
        assert parse_spanish_date("20/08", today=today) == date(2026, 8, 20)
        assert parse_spanish_date("20/08/2026", today=today) == date(2026, 8, 20)

    def test_garbage_returns_none(self):
        assert parse_spanish_date("no sé, cuando sea") is None
        assert parse_spanish_date("hola") is None


class TestFormatSpanishDate:
    def test_does_not_depend_on_server_locale(self):
        # 2026-08-08 is a Saturday — strftime('%A %d de %B') would render
        # "Saturday 08 de August" on a host without the es_MX locale installed.
        from datetime import datetime
        assert format_spanish_date(datetime(2026, 8, 8)) == "sábado 8 de agosto"

    def test_monday(self):
        from datetime import datetime
        assert format_spanish_date(datetime(2026, 8, 10)) == "lunes 10 de agosto"


async def _seed_user(**overrides):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", **overrides)
        db.add(user)
        await db.commit()
        return user.id


async def _seed_contact(advertiser_id, **overrides):
    async with AsyncSessionLocal() as db:
        contact = Contact(advertiser_id=advertiser_id, name="Ana Torres", phone="+525511112222", **overrides)
        db.add(contact)
        await db.commit()
        return contact.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Appointment).where(Appointment.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class _FakeRedis:
    """Minimal in-memory stand-in — real aioredis isn't running in this test
    style, and a real one would require infra just to exercise pure state
    transitions that don't care about network behavior."""
    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture
def fake_redis():
    return _FakeRedis()


class TestHandleAppointmentBooking:
    @pytest.mark.asyncio
    async def test_no_intent_returns_none(self, fake_redis):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                reply = await handle_appointment_booking(db, user, None, "¿cuál es su horario?", fake_redis)
            assert reply is None
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_intent_without_contact_invites_to_leave_data(self, fake_redis):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                reply = await handle_appointment_booking(db, user, None, "quiero agendar una cita", fake_redis)
            assert reply == NEEDS_CONTACT_REPLY
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_full_state_progression_to_confirmed(self, fake_redis):
        # every day open 9-11am so the test isn't flaky depending on when it runs
        user_id = await _seed_user(business_hours={
            "mon": ["09:00", "11:00"], "tue": ["09:00", "11:00"], "wed": ["09:00", "11:00"],
            "thu": ["09:00", "11:00"], "fri": ["09:00", "11:00"], "sat": ["09:00", "11:00"],
            "sun": ["09:00", "11:00"],
        })
        contact_id = await _seed_contact(user_id)
        try:
            with patch("app.core.email.send_new_appointment_email", new_callable=AsyncMock) as mock_email:
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    contact = await db.get(Contact, contact_id)
                    reply1 = await handle_appointment_booking(
                        db, user, contact, "quiero agendar una cita para corte de cabello", fake_redis
                    )
                assert "día" in reply1.lower()

                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    contact = await db.get(Contact, contact_id)
                    reply2 = await handle_appointment_booking(db, user, contact, "mañana", fake_redis)
                assert "1)" in reply2

                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    contact = await db.get(Contact, contact_id)
                    reply3 = await handle_appointment_booking(db, user, contact, "1", fake_redis)
                assert "nombre" in reply3.lower()

                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    contact = await db.get(Contact, contact_id)
                    reply4 = await handle_appointment_booking(db, user, contact, "Ana Torres", fake_redis)
                assert "confirmada" in reply4.lower()

                import asyncio
                await asyncio.sleep(0.05)
                assert mock_email.called

            async with AsyncSessionLocal() as db:
                appt = (
                    (await db.execute(
                        select(Appointment).where(Appointment.advertiser_id == user_id)
                    )).scalars().first()
                )
            assert appt.status == "confirmed"
            assert appt.customer_name == "Ana Torres"
            assert appt.service == "quiero agendar una cita para corte de cabello"
            assert appt.contact_id == contact_id
            # Redis state was cleared after completion
            assert fake_redis.store == {}
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_invalid_date_reprompts_same_step(self, fake_redis):
        user_id = await _seed_user()
        contact_id = await _seed_contact(user_id)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                await handle_appointment_booking(db, user, contact, "quiero agendar una cita", fake_redis)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                reply = await handle_appointment_booking(db, user, contact, "no sé cuándo", fake_redis)
            assert "no entendí" in reply.lower()
            import json
            state = json.loads(next(iter(fake_redis.store.values())))
            assert state["step"] == "collecting_date"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_closed_day_reprompts_for_another_date(self, fake_redis):
        user_id = await _seed_user(business_hours={"sun": None})
        contact_id = await _seed_contact(user_id)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                await handle_appointment_booking(db, user, contact, "quiero agendar una cita", fake_redis)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                reply = await handle_appointment_booking(db, user, contact, "domingo", fake_redis)
            assert "no tenemos horarios" in reply.lower()
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_out_of_range_slot_number_reprompts(self, fake_redis):
        user_id = await _seed_user(business_hours={
            "mon": ["09:00", "10:00"], "tue": ["09:00", "10:00"], "wed": ["09:00", "10:00"],
            "thu": ["09:00", "10:00"], "fri": ["09:00", "10:00"], "sat": ["09:00", "10:00"],
            "sun": ["09:00", "10:00"],
        })
        contact_id = await _seed_contact(user_id)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                await handle_appointment_booking(db, user, contact, "quiero agendar una cita", fake_redis)
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                await handle_appointment_booking(db, user, contact, "mañana", fake_redis)
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                reply = await handle_appointment_booking(db, user, contact, "99", fake_redis)
            assert "válido" in reply.lower() or "disponible" in reply.lower()
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_more_than_one_page_shows_mas_hint_and_paginates(self, fake_redis):
        """9am-6pm at 30-min steps is 18 slots — more than MAX_SLOTS_SHOWN (6).
        Previously the bot silently cut this to the first 6 (9:00-11:30am)
        and never showed the afternoon at all."""
        user_id = await _seed_user(business_hours={
            "mon": ["09:00", "18:00"], "tue": ["09:00", "18:00"], "wed": ["09:00", "18:00"],
            "thu": ["09:00", "18:00"], "fri": ["09:00", "18:00"], "sat": ["09:00", "18:00"],
            "sun": ["09:00", "18:00"],
        })
        contact_id = await _seed_contact(user_id)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                await handle_appointment_booking(db, user, contact, "quiero agendar una cita", fake_redis)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                reply_day = await handle_appointment_booking(db, user, contact, "mañana", fake_redis)
            assert "6)" in reply_day
            assert "7)" not in reply_day  # only the first page
            assert "MAS" in reply_day

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                reply_more = await handle_appointment_booking(db, user, contact, "mas", fake_redis)
            # Second page shows the next 6 (afternoon) slots, not a repeat of the first
            assert reply_more != reply_day
            assert "MAS" in reply_more  # 18 slots / 6 per page = 3 pages, more after page 2

            import json
            state = json.loads(next(iter(fake_redis.store.values())))
            assert state["offset"] == 6
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_single_page_has_no_mas_hint(self, fake_redis):
        user_id = await _seed_user(business_hours={
            "mon": ["09:00", "11:00"], "tue": ["09:00", "11:00"], "wed": ["09:00", "11:00"],
            "thu": ["09:00", "11:00"], "fri": ["09:00", "11:00"], "sat": ["09:00", "11:00"],
            "sun": ["09:00", "11:00"],
        })
        contact_id = await _seed_contact(user_id)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                await handle_appointment_booking(db, user, contact, "quiero agendar una cita", fake_redis)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                reply = await handle_appointment_booking(db, user, contact, "mañana", fake_redis)
            assert "MAS" not in reply
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_notifies_owner_via_whatsapp_only_when_connected(self, fake_redis):
        user_id = await _seed_user(
            whatsapp_number="+525500001111",
            business_hours={
                "mon": ["09:00", "11:00"], "tue": ["09:00", "11:00"], "wed": ["09:00", "11:00"],
                "thu": ["09:00", "11:00"], "fri": ["09:00", "11:00"], "sat": ["09:00", "11:00"],
                "sun": ["09:00", "11:00"],
            },
        )
        contact_id = await _seed_contact(user_id)
        try:
            with patch("app.core.email.send_new_appointment_email", new_callable=AsyncMock), \
                 patch("app.services.meta_service.send_whatsapp", new_callable=AsyncMock) as mock_wa:
                mock_wa.return_value = ("wamid.x", None)
                for msg in ["quiero agendar una cita", "mañana", "1", "Ana"]:
                    async with AsyncSessionLocal() as db:
                        user = await db.get(User, user_id)
                        contact = await db.get(Contact, contact_id)
                        await handle_appointment_booking(db, user, contact, msg, fake_redis)

                import asyncio
                await asyncio.sleep(0.05)
                mock_wa.assert_called_once()
                assert mock_wa.call_args.args[0] == "+525500001111"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_owner_notification_labels_the_real_channel(self, fake_redis):
        """Found in production 2026-08-12: the notification always said "(desde
        tu página web)" even for a booking made via WhatsApp — misleading the
        owner about where the customer actually came from."""
        user_id = await _seed_user(
            whatsapp_number="+525500001111",
            business_hours={
                "mon": ["09:00", "11:00"], "tue": ["09:00", "11:00"], "wed": ["09:00", "11:00"],
                "thu": ["09:00", "11:00"], "fri": ["09:00", "11:00"], "sat": ["09:00", "11:00"],
                "sun": ["09:00", "11:00"],
            },
        )
        contact_id = await _seed_contact(user_id)
        try:
            with patch("app.core.email.send_new_appointment_email", new_callable=AsyncMock), \
                 patch("app.services.meta_service.send_whatsapp", new_callable=AsyncMock) as mock_wa:
                mock_wa.return_value = ("wamid.x", None)
                for msg in ["quiero agendar una cita", "mañana", "1", "Ana"]:
                    async with AsyncSessionLocal() as db:
                        user = await db.get(User, user_id)
                        contact = await db.get(Contact, contact_id)
                        await handle_appointment_booking(db, user, contact, msg, fake_redis, channel="whatsapp")

                import asyncio
                await asyncio.sleep(0.05)
                body = mock_wa.call_args.args[1]
                assert "desde WhatsApp" in body
                assert "página web" not in body
        finally:
            await _cleanup([user_id])
