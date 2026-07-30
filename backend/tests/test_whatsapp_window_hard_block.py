"""
Tests for the 24h window hard block: campaigns and appointment reminders
must SKIP the send (not fall back to plain text) when the window is closed
and no approved template is available.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.whatsapp_window import is_window_open
from app.workers.task_helpers.campaign_ops import _ensure_conversation_window


def _conv(hours_ago: float | None):
    if hours_ago is None:
        return None
    conv = MagicMock()
    conv.last_activity = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return conv


class TestIsWindowOpen:
    def test_none_conversation_is_closed(self):
        assert is_window_open(None) is False

    def test_no_last_activity_is_closed(self):
        conv = MagicMock(last_activity=None)
        assert is_window_open(conv) is False

    def test_recent_activity_is_open(self):
        assert is_window_open(_conv(1)) is True

    def test_activity_23h_ago_is_open(self):
        assert is_window_open(_conv(23)) is True

    def test_activity_25h_ago_is_closed(self):
        assert is_window_open(_conv(25)) is False


class TestEnsureConversationWindowHardBlock:
    @pytest.mark.asyncio
    async def test_open_window_returns_zero_no_template_needed(self, test_user):
        db = AsyncMock()
        contact = MagicMock(id="c1", phone="+521234567890", name="Juan")
        convs = {"c1": _conv(1)}  # window open

        extra = await _ensure_conversation_window(db, test_user, contact, _convs=convs)
        assert extra == 0

    @pytest.mark.asyncio
    async def test_closed_window_no_template_returns_none(self, test_user):
        db = AsyncMock()
        contact = MagicMock(id="c1", phone="+521234567890", name="Juan")
        convs = {"c1": _conv(30)}  # window closed
        test_user.meta_utility_template_name = None

        extra = await _ensure_conversation_window(db, test_user, contact, _convs=convs)
        assert extra is None

    @pytest.mark.asyncio
    async def test_closed_window_template_send_fails_returns_none(self, test_user):
        db = AsyncMock()
        contact = MagicMock(id="c1", phone="+521234567890", name="Juan")
        convs = {"c1": _conv(30)}
        test_user.meta_utility_template_name = "notificacion_v2"

        with patch(
            "app.services.meta_service.send_whatsapp_template",
            new=AsyncMock(return_value=(None, "template rejected")),
        ):
            extra = await _ensure_conversation_window(db, test_user, contact, _convs=convs)
        assert extra is None

    @pytest.mark.asyncio
    async def test_closed_window_template_send_succeeds_returns_delay(self, mock_db, test_user):
        db = mock_db
        contact = MagicMock(id="c1", phone="+521234567890", name="Juan", consent_status="confirmed")
        convs = {"c1": None}  # no conversation yet, window closed
        test_user.meta_utility_template_name = "notificacion_v2"

        with patch(
            "app.services.meta_service.send_whatsapp_template",
            new=AsyncMock(return_value=("wamid.OK", None)),
        ):
            extra = await _ensure_conversation_window(db, test_user, contact, _convs=convs)
        assert extra is not None
        assert 10 <= extra <= 20

    @pytest.mark.asyncio
    async def test_closed_window_unconfirmed_consent_blocks_even_with_template(self, mock_db, test_user):
        """Cold, bulk-imported contact with no verified consent must never be
        reachable via a cold-window template reopen, even if the advertiser
        has an approved template configured — this is the anti-ban guard."""
        db = mock_db
        contact = MagicMock(id="c1", phone="+521234567890", name="Juan", consent_status="unconfirmed")
        convs = {"c1": None}
        test_user.meta_utility_template_name = "notificacion_v2"

        with patch(
            "app.services.meta_service.send_whatsapp_template",
            new=AsyncMock(return_value=("wamid.OK", None)),
        ) as mock_send:
            extra = await _ensure_conversation_window(db, test_user, contact, _convs=convs)
        assert extra is None
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_open_window_reaches_unconfirmed_contact_anyway(self, test_user):
        """Consent gate only blocks the cold-window reopen path — a contact
        who already has an open window (e.g. wrote in first) is unaffected
        regardless of consent_status."""
        db = AsyncMock()
        contact = MagicMock(id="c1", phone="+521234567890", name="Juan", consent_status="unconfirmed")
        convs = {"c1": _conv(1)}  # window open

        extra = await _ensure_conversation_window(db, test_user, contact, _convs=convs)
        assert extra == 0


class TestCampaignCallSitesSkipOnBlock:
    @pytest.mark.asyncio
    async def test_send_regular_messages_skips_blocked_contact(self, test_user):
        from app.workers.task_helpers.campaign_ops import send_regular_messages

        db = AsyncMock()
        campaign = MagicMock(id="camp1", advertiser_id=test_user.id, message_text="hola", ab_test={})
        contact = MagicMock(
            id="c1", phone="+521234567890", name="Juan", city=None, status="active",
            suppressed_until=None, last_campaign_sent_at=None, last_interaction=None,
            engagement_score=0,
        )
        test_user.messages_remaining = 100
        test_user.meta_utility_template_name = None  # can't reopen window

        with patch("app.workers.task_helpers.campaign_ops._preload_conversations", new=AsyncMock(return_value={"c1": None})), \
             patch("app.workers.task_helpers.campaign_ops._ensure_conversation_window", new=AsyncMock(return_value=None)) as mock_window, \
             patch("app.services.messaging_throttle.anti_ban_delay", return_value=1):
            await send_regular_messages(db, campaign, [contact], test_user, {}, ["hola"], ban_delay=0)

        mock_window.assert_called_once()
        # Must NOT have queued any send task or persisted an outbound message
        # for the blocked contact — db.add should not be called for a Message.
        assert not any(
            call.args and hasattr(call.args[0], "direction") for call in db.add.call_args_list
        )
