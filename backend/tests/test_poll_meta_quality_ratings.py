"""Tests for the poll_meta_quality_ratings Celery Beat task — the only
source of the real GREEN/YELLOW/RED rating (the webhook only ever carries
FLAGGED/UNFLAGGED, see meta_incoming.py)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.meta_client import MetaApiError
from app.workers.tasks import poll_meta_quality_ratings


def _db_with_advertisers(advertisers):
    db = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    result = MagicMock()
    result.scalars.return_value.all.return_value = advertisers
    db.execute = AsyncMock(return_value=result)
    return db


class TestPollMetaQualityRatings:
    def test_applies_rating_for_each_connected_advertiser(self, test_user):
        db = _db_with_advertisers([test_user])

        with patch("app.database.CeleryAsyncSessionLocal", return_value=db), \
             patch("app.services.meta_service._connection", return_value=("phone-1", "token-1")), \
             patch("app.services.meta_client.graph_request", new=AsyncMock(
                 return_value={"quality_rating": "YELLOW", "messaging_limit_tier": "TIER_1K"}
             )), \
             patch("app.services.meta_quality_service.apply_quality_signal", new=AsyncMock()) as mock_apply, \
             patch("app.workers.tasks.run_async", side_effect=lambda coro: asyncio.run(coro)):
            poll_meta_quality_ratings()

        mock_apply.assert_awaited_once_with(db, test_user, "YELLOW", "TIER_1K")

    def test_skips_advertiser_without_active_connection(self, test_user):
        db = _db_with_advertisers([test_user])

        with patch("app.database.CeleryAsyncSessionLocal", return_value=db), \
             patch("app.services.meta_service._connection", return_value=None), \
             patch("app.services.meta_client.graph_request", new=AsyncMock()) as mock_graph, \
             patch("app.services.meta_quality_service.apply_quality_signal", new=AsyncMock()) as mock_apply, \
             patch("app.workers.tasks.run_async", side_effect=lambda coro: asyncio.run(coro)):
            poll_meta_quality_ratings()

        mock_graph.assert_not_called()
        mock_apply.assert_not_called()

    def test_graph_api_failure_does_not_crash_and_skips_advertiser(self, test_user):
        db = _db_with_advertisers([test_user])

        with patch("app.database.CeleryAsyncSessionLocal", return_value=db), \
             patch("app.services.meta_service._connection", return_value=("phone-1", "token-1")), \
             patch("app.services.meta_client.graph_request", new=AsyncMock(
                 side_effect=MetaApiError("boom", status=500)
             )), \
             patch("app.services.meta_quality_service.apply_quality_signal", new=AsyncMock()) as mock_apply, \
             patch("app.workers.tasks.run_async", side_effect=lambda coro: asyncio.run(coro)):
            poll_meta_quality_ratings()  # must not raise

        mock_apply.assert_not_called()

    def test_persists_tier_even_without_a_rating(self, test_user):
        """Regresión Capa 10: antes, apply_quality_signal (y por tanto la
        persistencia del tier) solo se llamaba `if rating:` — si Meta
        devolvía messaging_limit_tier sin quality_rating, el tier se perdía
        silenciosamente. Debe llamarse igual cuando solo llega el tier."""
        db = _db_with_advertisers([test_user])

        with patch("app.database.CeleryAsyncSessionLocal", return_value=db), \
             patch("app.services.meta_service._connection", return_value=("phone-1", "token-1")), \
             patch("app.services.meta_client.graph_request", new=AsyncMock(
                 return_value={"messaging_limit_tier": "TIER_2K"}
             )), \
             patch("app.services.meta_quality_service.apply_quality_signal", new=AsyncMock()) as mock_apply, \
             patch("app.workers.tasks.run_async", side_effect=lambda coro: asyncio.run(coro)):
            poll_meta_quality_ratings()

        mock_apply.assert_awaited_once_with(db, test_user, None, "TIER_2K")
