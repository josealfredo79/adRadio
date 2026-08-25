"""Capa 16 anti-baneo, inbound half: once `_offer_or_send_radio_audio`
(campaign_ops.py) queues a [AUDIO-PENDING] Message for a contact with a
closed window, the actual audio is only sent here, in
inbound_pipeline.py, once the contact replies for real — a business-sent
template does not reopen the 24h window by itself (see
tests/test_radio_audio_optin.py for the send-side half of this fix).

Real DB (not mocks), same reasoning/pattern as
test_inbound_pipeline_handoff_triggers.py: process_inbound_message's early
gates chain many sequential db.execute() calls that are fragile to hand-mock
in exact order.
"""
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


async def _seed_with_pending_audio(phone_suffix: str):
    await engine.dispose()
    phone = f"+52123{phone_suffix}"
    async with AsyncSessionLocal() as db:
        advertiser = User(
            email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="IARadio Test",
            whatsapp_number="+525599990000", messages_remaining=50,
        )
        db.add(advertiser)
        await db.flush()

        contact = Contact(advertiser_id=advertiser.id, phone=phone, name="Cliente Test", status="active")
        db.add(contact)
        await db.flush()

        pending_msg = Message(
            advertiser_id=advertiser.id, contact_id=contact.id, direction="outbound",
            content="[AUDIO-PENDING] https://example.com/cuna.ogg", status="queued",
        )
        db.add(pending_msg)
        await db.commit()
        return advertiser.id, contact.id, pending_msg.id, phone


async def _get_message(message_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        return await db.get(Message, message_id)


async def _cleanup(advertiser_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Message).where(Message.advertiser_id == advertiser_id))
        await db.execute(delete(Conversation).where(Conversation.advertiser_id == advertiser_id))
        await db.execute(delete(Contact).where(Contact.advertiser_id == advertiser_id))
        await db.execute(delete(User).where(User.id == advertiser_id))
        await db.commit()
    await engine.dispose()


class TestAudioOptinConfirm:
    @pytest.mark.asyncio
    async def test_confirm_reply_sends_the_pending_audio(self):
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, pending_msg_id, phone = await _seed_with_pending_audio(f"2{run_id[:6]}")

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            msg = InboundMessage(
                advertiser=advertiser, from_number=phone,
                body_text="Si, escuchalo", external_message_id=f"wamid.{run_id}.in",
            )
            send = AsyncMock(return_value=(f"sid.{run_id}.out", None))
            send_owner = AsyncMock(return_value=(f"sid.{run_id}.owner", None))

            with patch(
                "app.services.meta_service.send_whatsapp_media",
                new=AsyncMock(return_value=("wamid.AUDIO.SENT", None)),
            ) as mock_send_media:
                result = await process_inbound_message(db, msg, send=send, send_owner=send_owner)

        try:
            assert result == {"message": "ok"}
            mock_send_media.assert_awaited_once()
            assert mock_send_media.call_args.args[0] == phone
            assert mock_send_media.call_args.args[1] == "https://example.com/cuna.ogg"

            pending_msg = await _get_message(pending_msg_id)
            assert pending_msg.status == "sent"
            assert pending_msg.wa_message_id == "wamid.AUDIO.SENT"

            send.assert_awaited_once()
            assert "Aquí tienes" in send.call_args.args[1]
        finally:
            await _cleanup(advertiser_id)

    @pytest.mark.asyncio
    async def test_decline_reply_does_not_send_audio(self):
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, pending_msg_id, phone = await _seed_with_pending_audio(f"3{run_id[:6]}")

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            msg = InboundMessage(
                advertiser=advertiser, from_number=phone,
                body_text="Ahora no", external_message_id=f"wamid.{run_id}.in",
            )
            send = AsyncMock(return_value=(f"sid.{run_id}.out", None))
            send_owner = AsyncMock(return_value=(f"sid.{run_id}.owner", None))

            with patch(
                "app.services.meta_service.send_whatsapp_media",
            ) as mock_send_media:
                result = await process_inbound_message(db, msg, send=send, send_owner=send_owner)

        try:
            assert result == {"message": "ok"}
            mock_send_media.assert_not_called()

            pending_msg = await _get_message(pending_msg_id)
            assert pending_msg.status == "failed"
            assert pending_msg.error_code == "declined_by_contact"

            send.assert_awaited_once()
            assert "Entendido" in send.call_args.args[1]
        finally:
            await _cleanup(advertiser_id)

    @pytest.mark.asyncio
    async def test_confirm_reply_is_idempotent_second_time(self):
        """Once fulfilled, a repeated 'sí' must not double-send the audio —
        the query only matches status='queued' rows."""
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, pending_msg_id, phone = await _seed_with_pending_audio(f"4{run_id[:6]}")

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            with patch(
                "app.services.meta_service.send_whatsapp_media",
                new=AsyncMock(return_value=("wamid.AUDIO.SENT", None)),
            ):
                await process_inbound_message(
                    db,
                    InboundMessage(advertiser=advertiser, from_number=phone, body_text="si", external_message_id=f"wamid.{run_id}.in1"),
                    send=AsyncMock(return_value=("s1", None)), send_owner=AsyncMock(return_value=("s1o", None)),
                )

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            with patch(
                "app.services.meta_service.send_whatsapp_media",
            ) as mock_send_media_2:
                await process_inbound_message(
                    db,
                    InboundMessage(advertiser=advertiser, from_number=phone, body_text="si", external_message_id=f"wamid.{run_id}.in2"),
                    send=AsyncMock(return_value=("s2", None)), send_owner=AsyncMock(return_value=("s2o", None)),
                )

        try:
            mock_send_media_2.assert_not_called()
        finally:
            await _cleanup(advertiser_id)
