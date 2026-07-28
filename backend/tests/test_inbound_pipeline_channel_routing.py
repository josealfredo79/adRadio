"""
Tests for inbound_pipeline.py's channel-aware column routing — the pipeline
writes/reads `twilio_sid` for channel="twilio" and `wa_message_id` for
channel="meta", so idempotency dedup and outbound SID persistence stay
correct for each transport now that both share one pipeline.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.inbound_pipeline import InboundMessage, process_inbound_message


def _existing_message_result(found: bool):
    result = MagicMock()
    result.scalar_one_or_none.return_value = MagicMock() if found else None
    return result


class TestIdempotencyColumnRouting:
    @pytest.mark.asyncio
    async def test_meta_channel_checks_wa_message_id_column(self, mock_db, test_user):
        mock_db.execute.return_value = _existing_message_result(found=True)

        msg = InboundMessage(
            advertiser=test_user,
            from_number="+521234567890",
            body_text="hola",
            external_message_id="wamid.DUP",
            channel="meta",
        )
        send = AsyncMock()
        result = await process_inbound_message(mock_db, msg, send=send, send_owner=send)

        assert result == {"message": "ok"}
        send.assert_not_called()  # short-circuited by idempotency check
        executed_stmt = str(mock_db.execute.call_args.args[0])
        # select(Message) always lists every column — check the WHERE clause specifically.
        assert "WHERE messages.wa_message_id" in executed_stmt
        assert "WHERE messages.twilio_sid" not in executed_stmt

    @pytest.mark.asyncio
    async def test_twilio_channel_checks_twilio_sid_column(self, mock_db, test_user):
        mock_db.execute.return_value = _existing_message_result(found=True)

        msg = InboundMessage(
            advertiser=test_user,
            from_number="+521234567890",
            body_text="hola",
            external_message_id="SM_DUP",
            channel="twilio",
        )
        send = AsyncMock()
        result = await process_inbound_message(mock_db, msg, send=send, send_owner=send)

        assert result == {"message": "ok"}
        executed_stmt = str(mock_db.execute.call_args.args[0])
        assert "WHERE messages.twilio_sid" in executed_stmt
        assert "WHERE messages.wa_message_id" not in executed_stmt

    @pytest.mark.asyncio
    async def test_default_channel_is_twilio(self):
        msg = InboundMessage(advertiser=MagicMock(), from_number="+52", body_text="x")
        assert msg.channel == "twilio"
