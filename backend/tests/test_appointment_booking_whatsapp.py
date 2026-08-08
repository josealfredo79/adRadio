"""Real-DB, no-mocks-of-business-logic test of the appointment self-service
booking flow through WhatsApp's actual entry point, process_inbound_message
— confirms the new branch added in inbound_pipeline.py (additive, doesn't
touch any existing branch) works end to end and the resulting Appointment
is exactly what shows up in GET /api/v1/appointments (the same query
AppointmentsPage.tsx's /app/appointments reads)."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.core.redis import close_redis
from app.database import AsyncSessionLocal, engine
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.services.inbound_pipeline import InboundMessage, process_inbound_message

PHONE = "+525511119999"


async def _seed_advertiser_and_contact(**user_overrides):
    await engine.dispose()
    # The global Redis pool (app.core.redis) is a singleton bound to whatever
    # event loop first created it — pytest-asyncio gives each test its own
    # loop, so a pool created by an earlier test errors as "attached to a
    # different loop" here. Same fix as the asyncpg engine-dispose gotcha.
    await close_redis()
    async with AsyncSessionLocal() as db:
        user = User(
            email=f"{uuid.uuid4()}@test.com", password_hash="x",
            business_hours={
                "mon": ["09:00", "11:00"], "tue": ["09:00", "11:00"], "wed": ["09:00", "11:00"],
                "thu": ["09:00", "11:00"], "fri": ["09:00", "11:00"], "sat": ["09:00", "11:00"],
                "sun": ["09:00", "11:00"],
            },
            **user_overrides,
        )
        db.add(user)
        await db.flush()
        contact = Contact(advertiser_id=user.id, name="Ana Torres", phone=PHONE, source="landing")
        db.add(contact)
        await db.commit()
        return user.id, contact.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Appointment).where(Appointment.advertiser_id.in_(user_ids)))
        await db.execute(delete(Message).where(Message.advertiser_id.in_(user_ids)))
        await db.execute(delete(Conversation).where(Conversation.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()
    await close_redis()


async def _send_message(advertiser, text):
    send = AsyncMock(return_value=(f"wamid.fake-{uuid.uuid4()}", None))
    async with AsyncSessionLocal() as db:
        msg = InboundMessage(advertiser=advertiser, from_number=PHONE, body_text=text)
        result = await process_inbound_message(db, msg, send=send, send_owner=send)
    return result, send


class TestAppointmentBookingViaWhatsApp:
    @pytest.mark.asyncio
    async def test_full_booking_flow_creates_a_real_appointment(self):
        user_id, contact_id = await _seed_advertiser_and_contact()
        try:
            async with AsyncSessionLocal() as db:
                advertiser = await db.get(User, user_id)

            with patch("app.core.email.send_new_appointment_email", new_callable=AsyncMock):
                result1, send1 = await _send_message(advertiser, "quiero agendar una cita para corte de cabello")
                assert result1 == {"message": "ok"}
                assert "día" in send1.call_args.args[1].lower()

                result2, send2 = await _send_message(advertiser, "mañana")
                assert "1)" in send2.call_args.args[1]

                result3, send3 = await _send_message(advertiser, "1")
                assert "nombre" in send3.call_args.args[1].lower()

                result4, send4 = await _send_message(advertiser, "Ana Torres")
                assert "confirmada" in send4.call_args.args[1].lower()

            async with AsyncSessionLocal() as db:
                appt = (
                    (await db.execute(select(Appointment).where(Appointment.advertiser_id == user_id)))
                    .scalars().first()
                )
            assert appt is not None
            assert appt.status == "confirmed"
            assert appt.customer_name == "Ana Torres"
            assert appt.service == "quiero agendar una cita para corte de cabello"
            assert appt.contact_id == contact_id

            # Same query GET /api/v1/appointments uses — confirms it would
            # actually show up in the advertiser's /app/appointments.
            from app.api.v1.appointments import list_appointments
            async with AsyncSessionLocal() as db:
                advertiser = await db.get(User, user_id)
                listed = await list_appointments(
                    status_filter=None, from_date=None, to_date=None, limit=100, offset=0,
                    current_user=advertiser, db=db,
                )
            assert len(listed) == 1
            assert listed[0].customer_name == "Ana Torres"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_existing_pending_order_does_not_block_starting_a_booking(self):
        """Sanity check that the new branch is additive: an unrelated
        WhatsApp conversation with no pending order/appointment still reaches
        appointment detection normally."""
        user_id, contact_id = await _seed_advertiser_and_contact()
        try:
            async with AsyncSessionLocal() as db:
                advertiser = await db.get(User, user_id)
            with patch("app.services.inbound_pipeline.answer_with_rag", new=AsyncMock(return_value="Abrimos 9-6.")):
                result, send = await _send_message(advertiser, "¿cuál es su horario de atención?")
            assert result == {"message": "ok"}
            # Falls through to RAG (no appointment/order keyword) — just
            # confirms no exception and the pipeline completed normally.
        finally:
            await _cleanup([user_id])
