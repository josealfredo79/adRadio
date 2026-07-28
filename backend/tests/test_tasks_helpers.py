"""Tests for Celery task helpers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from app.workers.task_helpers.common import run_async


class TestRunAsync:
    def test_run_async_basic(self):
        async def sample():
            return 42
        assert run_async(sample()) == 42

    def test_run_async_with_exception(self):
        async def failing():
            raise ValueError("test error")
        with pytest.raises(ValueError, match="test error"):
            run_async(failing())


class TestCampaignOps:
    @pytest.mark.asyncio
    async def test_notify_campaign_failed_no_campaign(self):
        from app.workers.task_helpers.campaign_ops import notify_campaign_failed
        result = await notify_campaign_failed("00000000-0000-0000-0000-000000000000", Exception("test"))
        assert result is None


class TestAppointmentOps:
    @pytest.mark.asyncio
    async def test_send_24h_reminders_empty(self):
        from app.workers.task_helpers.appointment_ops import send_24h_reminders
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        now = datetime.now(timezone.utc)
        result = await send_24h_reminders(mock_db, now)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_1h_reminders_empty(self):
        from app.workers.task_helpers.appointment_ops import send_1h_reminders
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        now = datetime.now(timezone.utc)
        result = await send_1h_reminders(mock_db, now)
        assert result is None
