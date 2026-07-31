"""Integration tests (real DB) for the two new handoff triggers in
inbound_pipeline.py: the customer explicitly asking for a human (backup
regex, ported from vocero-crm), and Claude/RAG failing outright. Both should
mark the conversation 'escalated' and notify the business owner — mirrors
vocero-crm's applyHandoff reasons 'cliente' and 'error'.

Uses a real DB session (not mocks) because process_inbound_message's early
gates (idempotency, human-handoff check, STOP-words, appointment/coupon
state machines) chain many sequential db.execute() calls that are fragile
to hand-mock in exact order — seeding real rows and asserting on real state
is more robust here, matching this repo's established real-DB test style
elsewhere (test_recipient_cap.py, test_ban_risk_autopause.py).

Every identifier that hits a UNIQUE constraint (phone, wa_message_id) is
suffixed with a fresh uuid per test run — this DB is the real shared Neon
instance, so a hardcoded literal reused across repeated local runs collides
with leftover rows from a prior run."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.services.inbound_pipeline import InboundMessage, process_inbound_message


async def _seed_advertiser_and_contact(phone_suffix: str):
    await engine.dispose()
    phone = f"+52123{phone_suffix}"
    async with AsyncSessionLocal() as db:
        advertiser = User(
            email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Panadería Test",
            whatsapp_number="+525599990000",
        )
        db.add(advertiser)
        await db.flush()

        contact = Contact(advertiser_id=advertiser.id, phone=phone, name="Cliente Test", status="active")
        db.add(contact)
        await db.commit()
        return advertiser.id, contact.id, phone


async def _get_conversation_status(advertiser_id, contact_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Conversation).where(
                Conversation.advertiser_id == advertiser_id,
                Conversation.contact_id == contact_id,
            )
        )
        conv = result.scalar_one_or_none()
        return conv.status if conv else None


async def _cleanup(advertiser_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Message).where(Message.advertiser_id == advertiser_id))
        await db.execute(delete(Conversation).where(Conversation.advertiser_id == advertiser_id))
        await db.execute(delete(Contact).where(Contact.advertiser_id == advertiser_id))
        await db.execute(delete(User).where(User.id == advertiser_id))
        await db.commit()
    # Leave no pooled connection tied to this loop for the next test — this
    # loop is about to be torn down between pytest-asyncio test functions.
    await engine.dispose()


class TestClientRequestedHandoff:
    @pytest.mark.asyncio
    async def test_explicit_human_request_escalates_and_notifies_owner(self):
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, phone = await _seed_advertiser_and_contact(f"0{run_id[:6]}")

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            msg = InboundMessage(
                advertiser=advertiser, from_number=phone,
                body_text="quiero hablar con un asesor", external_message_id=f"wamid.{run_id}.in",
            )
            send = AsyncMock(return_value=(f"sid.{run_id}.out", None))
            send_owner = AsyncMock(return_value=(f"sid.{run_id}.owner", None))

            result = await process_inbound_message(db, msg, send=send, send_owner=send_owner)

        try:
            assert result == {"message": "ok"}
            assert await _get_conversation_status(advertiser_id, contact_id) == "escalated"
            send.assert_awaited_once()
            assert "alguien del equipo" in send.call_args.args[1]
            send_owner.assert_awaited_once()
            assert "pidió hablar con una persona" in send_owner.call_args.args[1]
        finally:
            await _cleanup(advertiser_id)

    @pytest.mark.asyncio
    async def test_unrelated_message_does_not_escalate(self):
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, phone = await _seed_advertiser_and_contact(f"1{run_id[:6]}")

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            msg = InboundMessage(
                advertiser=advertiser, from_number=phone,
                body_text="hola, ¿tienen servicio a domicilio?", external_message_id=f"wamid.{run_id}.in",
            )
            send = AsyncMock(return_value=(f"sid.{run_id}.out", None))
            send_owner = AsyncMock(return_value=(f"sid.{run_id}.owner", None))

            with patch(
                "app.services.inbound_pipeline.answer_with_rag",
                new=AsyncMock(return_value="¡Sí, hacemos entregas a domicilio!"),
            ):
                await process_inbound_message(db, msg, send=send, send_owner=send_owner)

        try:
            assert await _get_conversation_status(advertiser_id, contact_id) != "escalated"
            send_owner.assert_not_awaited()
        finally:
            await _cleanup(advertiser_id)


class TestBotErrorHandoff:
    @pytest.mark.asyncio
    async def test_claude_failure_escalates_and_notifies_owner(self):
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, phone = await _seed_advertiser_and_contact(f"2{run_id[:6]}")

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            msg = InboundMessage(
                advertiser=advertiser, from_number=phone,
                body_text="¿tienen pan sin gluten?", external_message_id=f"wamid.{run_id}.in",
            )
            send = AsyncMock(return_value=(f"sid.{run_id}.out", None))
            send_owner = AsyncMock(return_value=(f"sid.{run_id}.owner", None))

            with patch(
                "app.services.inbound_pipeline.answer_with_rag",
                new=AsyncMock(side_effect=RuntimeError("Claude API down")),
            ):
                result = await process_inbound_message(db, msg, send=send, send_owner=send_owner)

        try:
            assert result == {"message": "ok"}
            assert await _get_conversation_status(advertiser_id, contact_id) == "escalated"
            send.assert_awaited_once()
            assert "problema técnico" in send.call_args.args[1]
            send_owner.assert_awaited_once()
            assert "el bot falló" in send_owner.call_args.args[1].lower()
        finally:
            await _cleanup(advertiser_id)
