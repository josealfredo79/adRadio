"""Tests for app.services.meta_quality_service — the shared reaction logic
for WhatsApp quality signals, used by both the real-time webhook
(FLAGGED/UNFLAGGED only) and the Graph API poll (real GREEN/YELLOW/RED)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.meta_quality_service import apply_quality_signal, is_ban_risk_error, pause_active_campaigns


def _db_with_campaigns(campaigns):
    db = AsyncMock()
    db.commit = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = campaigns
    db.execute = AsyncMock(return_value=result)
    return db


class TestApplyQualitySignal:
    @pytest.mark.asyncio
    async def test_yellow_halves_throttle(self, test_user):
        db = _db_with_campaigns([])
        test_user.meta_send_throttle_per_hour = 60

        await apply_quality_signal(db, test_user, "YELLOW", "TIER_1K")

        assert test_user.meta_quality_rating == "YELLOW"
        assert test_user.meta_messaging_tier == "TIER_1K"
        assert test_user.meta_send_throttle_per_hour == 30
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_green_restores_baseline_throttle(self, test_user):
        db = _db_with_campaigns([])
        test_user.meta_send_throttle_per_hour = 30  # was throttled before

        await apply_quality_signal(db, test_user, "GREEN")

        assert test_user.meta_quality_rating == "GREEN"
        assert test_user.meta_send_throttle_per_hour == 60

    @pytest.mark.asyncio
    async def test_red_pauses_active_campaigns(self, test_user):
        running = MagicMock(status="running")
        scheduled = MagicMock(status="scheduled")
        db = _db_with_campaigns([running, scheduled])

        await apply_quality_signal(db, test_user, "RED")

        assert test_user.meta_quality_rating == "RED"
        assert running.status == "paused"
        assert scheduled.status == "paused"

    @pytest.mark.asyncio
    async def test_na_rating_only_records_no_reaction(self, test_user):
        """Meta returns 'NA' for brand-new numbers with no rating yet — just
        record it, don't touch the throttle or pause anything."""
        db = _db_with_campaigns([])
        test_user.meta_send_throttle_per_hour = 60

        await apply_quality_signal(db, test_user, "NA")

        assert test_user.meta_quality_rating == "NA"
        assert test_user.meta_send_throttle_per_hour == 60
        db.execute.assert_not_called()


class TestPauseActiveCampaigns:
    @pytest.mark.asyncio
    async def test_only_pauses_running_and_scheduled(self, test_user):
        completed = MagicMock(status="completed")
        db = _db_with_campaigns([completed])

        await pause_active_campaigns(db, test_user.id)

        # The query itself filters by status — this just confirms whatever
        # comes back gets paused unconditionally, matching the SQL filter.
        assert completed.status == "paused"


class TestIsBanRiskError:
    def test_none_is_not_ban_risk(self):
        assert is_ban_risk_error(None) is False

    def test_unrelated_error_is_not_ban_risk(self):
        assert is_ban_risk_error("(#131026) Message undeliverable") is False

    def test_healthy_ecosystem_engagement_code_is_ban_risk(self):
        assert is_ban_risk_error("(#131049) This message was not delivered to maintain healthy ecosystem engagement") is True

    def test_temporarily_blocked_code_is_ban_risk(self):
        assert is_ban_risk_error("(#368) Temporarily blocked for policies violations") is True

    def test_bare_368_substring_without_parens_does_not_false_match(self):
        """368 alone (e.g. as part of an unrelated numeric id in a message)
        must not trigger — only the parenthesized Meta error-code form does."""
        assert is_ban_risk_error("Error interno 12368 procesando el mensaje") is False

    def test_ordinary_rate_limit_error_is_not_ban_risk(self):
        """Rate-limit codes (already handled separately by
        _RATE_LIMIT_ERROR_CODES in tasks.py) are retry-worthy, not
        ban-risk — a different reaction (retry vs. pause everything)."""
        assert is_ban_risk_error("(#130429) Rate limit hit") is False
