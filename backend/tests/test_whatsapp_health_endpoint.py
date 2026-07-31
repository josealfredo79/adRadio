"""Tests for GET /me/whatsapp-health (Capa 15 anti-baneo) — the account
health snapshot surfacing what capas 6-14 compute in the background
(quality rating, tier, warm-up ramp, effective recipient cap, active/paused
campaign counts) so the advertiser isn't left guessing why sends stopped."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.api.deps import get_current_user
from app.database import get_db


@pytest.fixture
def client(test_user):
    async def _fake_user():
        return test_user

    main_module.app.dependency_overrides[get_current_user] = _fake_user
    yield TestClient(main_module.app)
    main_module.app.dependency_overrides.clear()


def _install_db(recipient_count: int, campaign_counts: list[tuple[str, int]]):
    """First db.execute call is get_recipient_cap_state's RecipientSend
    count query, second is this endpoint's campaign status GROUP BY."""
    recipient_result = MagicMock()
    recipient_result.scalar_one.return_value = recipient_count
    campaign_result = MagicMock()
    campaign_result.all.return_value = campaign_counts

    async def _fake_db():
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[recipient_result, campaign_result])
        yield db

    main_module.app.dependency_overrides[get_db] = _fake_db


class TestWhatsappHealth:
    def test_healthy_established_number_reports_no_restrictions(self, client, test_user):
        test_user.meta_quality_rating = "GREEN"
        test_user.meta_messaging_tier = "TIER_1K"
        test_user.meta_send_throttle_per_hour = 60
        test_user.meta_connected_at = datetime.now(timezone.utc) - timedelta(days=90)
        _install_db(recipient_count=40, campaign_counts=[("running", 2), ("paused", 0)])

        r = client.get("/api/v1/me/whatsapp-health")

        assert r.status_code == 200
        data = r.json()
        assert data["quality_rating"] == "GREEN"
        assert data["tier_recipient_limit"] == 1000
        assert data["warmup_active"] is False
        assert data["warmup_recipient_cap"] is None
        assert data["warmup_days_remaining"] is None
        assert data["recipients_sent_last_24h"] == 40
        assert data["effective_recipient_limit"] == 1000
        assert data["active_campaigns_count"] == 2
        assert data["paused_campaigns_count"] == 0

    def test_brand_new_number_reports_warmup_state(self, client, test_user):
        test_user.meta_quality_rating = None
        test_user.meta_messaging_tier = None
        test_user.meta_connected_at = datetime.now(timezone.utc)  # just connected
        _install_db(recipient_count=3, campaign_counts=[("running", 1)])

        r = client.get("/api/v1/me/whatsapp-health")

        assert r.status_code == 200
        data = r.json()
        assert data["warmup_active"] is True
        assert data["warmup_recipient_cap"] == 20
        assert data["warmup_days_remaining"] == pytest.approx(29, abs=0.1)
        # No tier known yet -> default tier limit (250) but warmup (20) still wins.
        assert data["effective_recipient_limit"] == 20

    def test_paused_campaigns_are_counted_separately_from_active(self, client, test_user):
        test_user.meta_connected_at = None
        _install_db(recipient_count=0, campaign_counts=[("running", 1), ("scheduled", 2), ("paused", 3)])

        r = client.get("/api/v1/me/whatsapp-health")

        data = r.json()
        assert data["active_campaigns_count"] == 3  # running + scheduled
        assert data["paused_campaigns_count"] == 3

    def test_no_campaigns_at_all_reports_zero_not_error(self, client, test_user):
        test_user.meta_connected_at = None
        _install_db(recipient_count=0, campaign_counts=[])

        r = client.get("/api/v1/me/whatsapp-health")

        assert r.status_code == 200
        data = r.json()
        assert data["active_campaigns_count"] == 0
        assert data["paused_campaigns_count"] == 0
