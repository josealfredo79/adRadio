"""
Tests for the human-handoff guardrail in inbound_pipeline.py: once a
Conversation is 'escalated', the bot must not auto-reply — no STOP-words,
no appointment/order state machines, no RAG.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.inbound_pipeline import InboundMessage, process_inbound_message


def _contact_and_escalated_conv():
    contact = MagicMock(id="contact-1")
    conv = MagicMock(id="conv-1", status="escalated")
    return contact, conv


class TestHandoffGuardrail:
    @pytest.mark.asyncio
    async def test_escalated_conversation_skips_rag_and_does_not_send(self, mock_db, test_user):
        contact, conv = _contact_and_escalated_conv()

        contact_result = MagicMock()
        contact_result.scalar_one_or_none.return_value = contact
        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv
        no_dup_result = MagicMock()
        no_dup_result.scalar_one_or_none.return_value = None

        # Order of db.execute calls in the pipeline: idempotency check,
        # contact lookup, escalated-conversation lookup.
        mock_db.execute.side_effect = [no_dup_result, contact_result, conv_result]

        msg = InboundMessage(
            advertiser=test_user,
            from_number="+521234567890",
            body_text="¿siguen las promociones?",
            external_message_id="wamid.ESC1",
            channel="meta",
        )
        send = AsyncMock()

        with patch("app.services.inbound_pipeline.answer_with_rag", new=AsyncMock()) as mock_rag:
            result = await process_inbound_message(mock_db, msg, send=send, send_owner=send)

        assert result == {"message": "ok"}
        send.assert_not_called()
        mock_rag.assert_not_called()
        assert conv.last_activity is not None  # updated via func.now()

    @pytest.mark.asyncio
    async def test_escalated_conversation_still_logs_inbound_message(self, mock_db, test_user):
        contact, conv = _contact_and_escalated_conv()

        contact_result = MagicMock()
        contact_result.scalar_one_or_none.return_value = contact
        conv_result = MagicMock()
        conv_result.scalar_one_or_none.return_value = conv
        no_dup_result = MagicMock()
        no_dup_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [no_dup_result, contact_result, conv_result]

        msg = InboundMessage(
            advertiser=test_user,
            from_number="+521234567890",
            body_text="hola humano",
            external_message_id="wamid.ESC2",
            channel="meta",
        )
        send = AsyncMock()

        with patch("app.services.inbound_pipeline.answer_with_rag", new=AsyncMock()):
            await process_inbound_message(mock_db, msg, send=send, send_owner=send)

        # db.add was called once with a Message row for the handoff log.
        assert mock_db.add.call_count == 1
        added_msg = mock_db.add.call_args.args[0]
        assert added_msg.content == "hola humano"
        assert added_msg.direction == "inbound"

    @pytest.mark.asyncio
    async def test_non_escalated_conversation_proceeds_normally(self, mock_db, test_user):
        """No existing contact at all -> not escalated -> pipeline continues
        (this test only asserts it does NOT short-circuit at the handoff gate;
        it may still fail deeper in the pipeline due to further mocking gaps,
        which is fine — we only care that answer_with_rag path is reachable)."""
        contact_result = MagicMock()
        contact_result.scalar_one_or_none.return_value = None  # no contact yet
        no_dup_result = MagicMock()
        no_dup_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [no_dup_result, contact_result]

        msg = InboundMessage(
            advertiser=test_user,
            from_number="+521234567890",
            body_text="hola",
            external_message_id="wamid.NEW1",
            channel="meta",
        )
        send = AsyncMock()

        # Let it run as far as it can; assert it did NOT take the handoff
        # early-return path (send would eventually be attempted somewhere
        # downstream once contact/conversation get created, but at minimum
        # it must not stop after only 2 db.execute calls with zero db.add).
        try:
            await process_inbound_message(mock_db, msg, send=send, send_owner=send)
        except StopAsyncIteration:
            pass  # ran out of mocked side_effects further down the pipeline — expected
        assert mock_db.execute.call_count > 2  # got past the handoff gate, kept querying deeper
