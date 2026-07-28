"""Tests for app.services.lab.runner — mocked simulator/judge, real orchestration logic."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.lab.personas import PERSONAS
from app.services.lab.runner import run_lab


def _lab_run_result(lab_run):
    r = MagicMock()
    r.scalar_one_or_none.return_value = lab_run
    return r


def _user_result(user):
    r = MagicMock()
    r.scalar_one_or_none.return_value = user
    return r


class TestRunLab:
    @pytest.mark.asyncio
    async def test_unknown_lab_run_id_is_noop(self, mock_db):
        mock_db.execute.return_value = _lab_run_result(None)
        await run_lab(str(uuid.uuid4()), mock_db)
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_advertiser_marks_error(self, mock_db):
        lab_run = MagicMock(id=uuid.uuid4(), advertiser_id=uuid.uuid4())
        mock_db.execute.side_effect = [_lab_run_result(lab_run), _user_result(None)]

        await run_lab(str(lab_run.id), mock_db)

        assert lab_run.status == "error"
        assert "no encontrado" in lab_run.error_message
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_successful_run_processes_all_personas_and_averages_score(self, mock_db, test_user):
        lab_run = MagicMock(id=uuid.uuid4(), advertiser_id=test_user.id)
        mock_db.execute.side_effect = [_lab_run_result(lab_run), _user_result(test_user)]

        scores = [80, 90, 70, 60, 100, 50]  # avg = 75
        eval_results = [{"score": s, "summary": "ok", "findings": []} for s in scores]

        with patch(
            "app.services.lab.runner.run_persona_conversation",
            new=AsyncMock(return_value=[{"role": "user", "content": "hola"}]),
        ), patch(
            "app.services.lab.runner.evaluate_transcript",
            new=AsyncMock(side_effect=eval_results),
        ):
            await run_lab(str(lab_run.id), mock_db)

        assert lab_run.status == "completed"
        assert lab_run.overall_score == 75
        assert lab_run.completed_at is not None
        assert mock_db.add.call_count == len(PERSONAS)

    @pytest.mark.asyncio
    async def test_exception_mid_run_marks_error_and_rolls_back(self, mock_db, test_user):
        lab_run = MagicMock(id=uuid.uuid4(), advertiser_id=test_user.id)
        # First two execute() calls resolve lab_run + advertiser; the third
        # (inside the except re-fetch) resolves lab_run again.
        mock_db.execute.side_effect = [
            _lab_run_result(lab_run),
            _user_result(test_user),
            _lab_run_result(lab_run),
        ]

        with patch(
            "app.services.lab.runner.run_persona_conversation",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await run_lab(str(lab_run.id), mock_db)

        assert lab_run.status == "error"
        assert "boom" in lab_run.error_message
        mock_db.rollback.assert_called_once()
