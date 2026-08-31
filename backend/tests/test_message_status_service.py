"""Tests for app.services.message_status_service.apply_status_update."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.message_status_service import apply_status_update


def _msg_result(msg):
    r = MagicMock()
    r.scalar_one_or_none.return_value = msg
    return r


class TestApplyStatusUpdate:
    @pytest.mark.asyncio
    async def test_missing_wa_message_id_is_noop(self, mock_db):
        await apply_status_update(mock_db, "", "delivered")
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_message_is_noop(self, mock_db):
        mock_db.execute.return_value = _msg_result(None)
        await apply_status_update(mock_db, "wamid.X", "delivered")
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_delivered_sets_timestamp_and_publishes(self, mock_db):
        msg = MagicMock(
            status="sent", delivered_at=None, read_at=None, campaign_id=None,
            contact_id=uuid.uuid4(), advertiser_id=uuid.uuid4(),
        )
        mock_db.execute.return_value = _msg_result(msg)

        with patch("app.services.message_status_service.publish_conversation_event", new=AsyncMock()) as mock_pub:
            await apply_status_update(mock_db, "wamid.X", "delivered")

        assert msg.status == "delivered"
        assert msg.delivered_at is not None
        mock_db.commit.assert_called_once()
        mock_pub.assert_called_once_with(msg.advertiser_id, {"type": "status", "contact_id": str(msg.contact_id)})

    @pytest.mark.asyncio
    async def test_no_contact_id_skips_publish(self, mock_db):
        msg = MagicMock(status="sent", delivered_at=None, read_at=None, campaign_id=None, contact_id=None)
        mock_db.execute.return_value = _msg_result(msg)

        with patch("app.services.message_status_service.publish_conversation_event", new=AsyncMock()) as mock_pub:
            await apply_status_update(mock_db, "wamid.X", "read")

        mock_pub.assert_not_called()

    @pytest.mark.asyncio
    async def test_campaign_stats_not_touched_on_status_change(self, mock_db):
        # Campaign engagement stats are derived live from messages.status
        # (campaign_stats_service) — apply_status_update must NOT bump a
        # Campaign.stats counter, else duplicate/reordered WhatsApp
        # receipts drift delivered/read above sent.
        msg = MagicMock(
            status="sent", delivered_at=None, read_at=None,
            campaign_id=uuid.uuid4(), contact_id=uuid.uuid4(), advertiser_id=uuid.uuid4(),
        )
        mock_db.execute.return_value = _msg_result(msg)

        with patch("app.services.message_status_service.publish_conversation_event", new=AsyncMock()):
            await apply_status_update(mock_db, "wamid.X", "delivered")

        # only the message lookup — no follow-up Campaign query
        assert mock_db.execute.call_count == 1
        assert msg.status == "delivered"

    @pytest.mark.asyncio
    async def test_unmapped_status_keeps_existing_status(self, mock_db):
        msg = MagicMock(
            status="sent", delivered_at=None, read_at=None, campaign_id=None,
            contact_id=uuid.uuid4(), advertiser_id=uuid.uuid4(),
        )
        mock_db.execute.return_value = _msg_result(msg)

        with patch("app.services.message_status_service.publish_conversation_event", new=AsyncMock()):
            await apply_status_update(mock_db, "wamid.X", "some_unknown_status")

        assert msg.status == "sent"
