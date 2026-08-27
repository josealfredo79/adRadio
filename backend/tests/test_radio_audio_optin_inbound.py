"""Capa 16 anti-baneo, inbound half: once `_offer_or_queue` (campaign_ops.py)
queues a `[PENDING:<kind>]` Message for a contact with a closed window, the
actual content is only sent here, in inbound_pipeline.py, once the contact
replies for real — a business-sent template does not reopen the 24h window
by itself (see tests/test_radio_audio_optin.py for the send-side half of
this fix).

On the contact's reply the pending row is rewritten to its real marker
(`[AUDIO]` / `[BANNER]` / plain body) and dispatched through the SAME Celery
send task the open-window path uses (retries, auto-suppression, ban-risk
detection, single quota decrement). It does NOT early-return: the reply then
keeps flowing through the normal pipeline, so it gets persisted (shows in
the Inbox), the contact is marked `consent_status="confirmed"` (this reply
IS the opt-in proof), the window is reopened locally, and any real intent in
the reply still gets answered by the bot.

Real DB (not mocks), same reasoning/pattern as
test_inbound_pipeline_handoff_triggers.py: process_inbound_message's early
gates chain many sequential db.execute() calls that are fragile to hand-mock
in exact order.
"""
import json
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

# The resume now falls through to the RAG bot for any reply that isn't an
# explicit decline — patch it everywhere so tests never hit a real LLM.
_RAG_PATCH = "app.services.inbound_pipeline.answer_with_rag"
_RAG_REPLY = "Gracias por tu mensaje, ¿en qué más te ayudo?"

_VOICE_TASK = "app.workers.tasks.send_whatsapp_voice_note.apply_async"
_IMAGE_TASK = "app.workers.tasks.send_whatsapp_image_message.apply_async"
_TEXT_TASK = "app.workers.tasks.send_whatsapp_message.apply_async"


async def _seed_with_pending(phone_suffix: str, kind: str, payload: dict):
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
            content=f"[PENDING:{kind}] {json.dumps(payload)}", status="queued",
        )
        db.add(pending_msg)
        await db.commit()
        return advertiser.id, contact.id, pending_msg.id, phone


async def _get_message(message_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        return await db.get(Message, message_id)


async def _get_contact(contact_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        return await db.get(Contact, contact_id)


async def _inbound_messages(advertiser_id, contact_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Message).where(
                Message.advertiser_id == advertiser_id,
                Message.contact_id == contact_id,
                Message.direction == "inbound",
            )
        )
        return rows.scalars().all()


async def _cleanup(advertiser_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Message).where(Message.advertiser_id == advertiser_id))
        await db.execute(delete(Conversation).where(Conversation.advertiser_id == advertiser_id))
        await db.execute(delete(Contact).where(Contact.advertiser_id == advertiser_id))
        await db.execute(delete(User).where(User.id == advertiser_id))
        await db.commit()
    await engine.dispose()


class TestPendingAudioConfirm:
    @pytest.mark.asyncio
    async def test_confirm_reply_dispatches_the_pending_audio(self):
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, pending_msg_id, phone = await _seed_with_pending(
            f"2{run_id[:6]}", "audio", {"audio_url": "https://example.com/cuna.ogg", "script": "test script"},
        )

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            msg = InboundMessage(
                advertiser=advertiser, from_number=phone,
                body_text="Si, escuchalo", external_message_id=f"wamid.{run_id}.in",
            )
            send = AsyncMock(return_value=(f"sid.{run_id}.out", None))
            send_owner = AsyncMock(return_value=(f"sid.{run_id}.owner", None))

            with patch(_VOICE_TASK) as mock_task, patch(_RAG_PATCH, new=AsyncMock(return_value=_RAG_REPLY)):
                result = await process_inbound_message(db, msg, send=send, send_owner=send_owner)

        try:
            assert result == {"message": "ok"}
            mock_task.assert_called_once()
            assert mock_task.call_args.kwargs["args"][0] == str(pending_msg_id)
            assert mock_task.call_args.kwargs["args"][1] == phone
            assert mock_task.call_args.kwargs["args"][2] == "https://example.com/cuna.ogg"
            assert mock_task.call_args.kwargs["args"][3] == "test script"

            # The pending row is rewritten to its real marker and left queued
            # for the task to finalize.
            pending_msg = await _get_message(pending_msg_id)
            assert pending_msg.content == "[AUDIO] https://example.com/cuna.ogg"
            assert pending_msg.status == "queued"

            # B fix: the reply that resumed the send is not swallowed — it is
            # persisted and the contact is now a confirmed opt-in.
            inbound = await _inbound_messages(advertiser_id, contact_id)
            assert [m.content for m in inbound] == ["Si, escuchalo"]
            contact = await _get_contact(contact_id)
            assert contact.consent_status == "confirmed"
        finally:
            await _cleanup(advertiser_id)

    @pytest.mark.asyncio
    async def test_any_non_decline_reply_also_resumes_and_still_answers(self):
        """The reopen template configured for most advertisers today
        (`meta_utility_template_name`) has no Sí/No buttons — so ANY genuine
        reply (not just an exact "sí") must resume the deferred send, since
        that's what actually reopens the window per Meta's rules. And because
        the resume no longer early-returns, a reply that carries real intent
        still reaches the bot (A fix)."""
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, pending_msg_id, phone = await _seed_with_pending(
            f"5{run_id[:6]}", "audio", {"audio_url": "https://example.com/cuna.ogg", "script": "test script"},
        )

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            msg = InboundMessage(
                advertiser=advertiser, from_number=phone,
                body_text="Gracias, ¿tienen envío a domicilio?", external_message_id=f"wamid.{run_id}.in",
            )
            send = AsyncMock(return_value=(f"sid.{run_id}.out", None))
            send_owner = AsyncMock(return_value=(f"sid.{run_id}.owner", None))

            with patch(_VOICE_TASK) as mock_task, patch(_RAG_PATCH, new=AsyncMock(return_value=_RAG_REPLY)) as mock_rag:
                result = await process_inbound_message(db, msg, send=send, send_owner=send_owner)

        try:
            assert result == {"message": "ok"}
            mock_task.assert_called_once()

            pending_msg = await _get_message(pending_msg_id)
            assert pending_msg.content == "[AUDIO] https://example.com/cuna.ogg"

            # A fix: the question still got answered by the bot.
            mock_rag.assert_awaited_once()
            assert any(_RAG_REPLY in c.args[1] for c in send.call_args_list)
        finally:
            await _cleanup(advertiser_id)

    @pytest.mark.asyncio
    async def test_decline_reply_does_not_dispatch_audio(self):
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, pending_msg_id, phone = await _seed_with_pending(
            f"3{run_id[:6]}", "audio", {"audio_url": "https://example.com/cuna.ogg", "script": "test script"},
        )

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            msg = InboundMessage(
                advertiser=advertiser, from_number=phone,
                body_text="Ahora no", external_message_id=f"wamid.{run_id}.in",
            )
            send = AsyncMock(return_value=(f"sid.{run_id}.out", None))
            send_owner = AsyncMock(return_value=(f"sid.{run_id}.owner", None))

            with patch(_VOICE_TASK) as mock_task, patch(_RAG_PATCH, new=AsyncMock(return_value=_RAG_REPLY)):
                result = await process_inbound_message(db, msg, send=send, send_owner=send_owner)

        try:
            assert result == {"message": "ok"}
            mock_task.assert_not_called()

            pending_msg = await _get_message(pending_msg_id)
            assert pending_msg.status == "failed"
            assert pending_msg.error_code == "declined_by_contact"

            # The decline is still a real reply — recorded, not swallowed.
            inbound = await _inbound_messages(advertiser_id, contact_id)
            assert [m.content for m in inbound] == ["Ahora no"]
        finally:
            await _cleanup(advertiser_id)

    @pytest.mark.asyncio
    async def test_confirm_reply_is_idempotent_second_time(self):
        """Once the pending row is rewritten to [AUDIO], a repeated reply
        must not re-dispatch — the query only matches queued [PENDING:%
        rows."""
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, pending_msg_id, phone = await _seed_with_pending(
            f"4{run_id[:6]}", "audio", {"audio_url": "https://example.com/cuna.ogg", "script": "test script"},
        )

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            with patch(_VOICE_TASK), patch(_RAG_PATCH, new=AsyncMock(return_value=_RAG_REPLY)):
                await process_inbound_message(
                    db,
                    InboundMessage(advertiser=advertiser, from_number=phone, body_text="si", external_message_id=f"wamid.{run_id}.in1"),
                    send=AsyncMock(return_value=("s1", None)), send_owner=AsyncMock(return_value=("s1o", None)),
                )

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            with patch(_VOICE_TASK) as mock_task_2, patch(_RAG_PATCH, new=AsyncMock(return_value=_RAG_REPLY)):
                await process_inbound_message(
                    db,
                    InboundMessage(advertiser=advertiser, from_number=phone, body_text="si", external_message_id=f"wamid.{run_id}.in2"),
                    send=AsyncMock(return_value=("s2", None)), send_owner=AsyncMock(return_value=("s2o", None)),
                )

        try:
            mock_task_2.assert_not_called()
        finally:
            await _cleanup(advertiser_id)


class TestPendingBannerConfirm:
    @pytest.mark.asyncio
    async def test_confirm_reply_dispatches_the_pending_banner(self):
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, pending_msg_id, phone = await _seed_with_pending(
            f"6{run_id[:6]}", "banner", {"banner_url": "https://example.com/banner.png", "caption": "¡Mira esto!"},
        )

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            msg = InboundMessage(
                advertiser=advertiser, from_number=phone,
                body_text="ok", external_message_id=f"wamid.{run_id}.in",
            )
            send = AsyncMock(return_value=(f"sid.{run_id}.out", None))
            send_owner = AsyncMock(return_value=(f"sid.{run_id}.owner", None))

            with patch(_IMAGE_TASK) as mock_task, patch(_RAG_PATCH, new=AsyncMock(return_value=_RAG_REPLY)):
                result = await process_inbound_message(db, msg, send=send, send_owner=send_owner)

        try:
            assert result == {"message": "ok"}
            mock_task.assert_called_once()
            assert mock_task.call_args.kwargs["args"][1] == phone
            assert mock_task.call_args.kwargs["args"][2] == "https://example.com/banner.png"
            assert mock_task.call_args.kwargs["args"][3] == "¡Mira esto!"

            pending_msg = await _get_message(pending_msg_id)
            assert pending_msg.content == "[BANNER] https://example.com/banner.png"
        finally:
            await _cleanup(advertiser_id)


class TestPendingTextConfirm:
    @pytest.mark.asyncio
    async def test_confirm_reply_dispatches_the_pending_text(self):
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, pending_msg_id, phone = await _seed_with_pending(
            f"7{run_id[:6]}", "text", {"body": "Hola, tenemos una promo para ti"},
        )

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            msg = InboundMessage(
                advertiser=advertiser, from_number=phone,
                body_text="claro", external_message_id=f"wamid.{run_id}.in",
            )
            send = AsyncMock(return_value=(f"sid.{run_id}.out", None))
            send_owner = AsyncMock(return_value=(f"sid.{run_id}.owner", None))

            with patch(_TEXT_TASK) as mock_task, patch(_RAG_PATCH, new=AsyncMock(return_value=_RAG_REPLY)):
                result = await process_inbound_message(db, msg, send=send, send_owner=send_owner)

        try:
            assert result == {"message": "ok"}
            mock_task.assert_called_once()
            assert mock_task.call_args.kwargs["args"][1] == phone
            assert mock_task.call_args.kwargs["args"][2] == "Hola, tenemos una promo para ti"

            pending_msg = await _get_message(pending_msg_id)
            assert pending_msg.content == "Hola, tenemos una promo para ti"
        finally:
            await _cleanup(advertiser_id)
