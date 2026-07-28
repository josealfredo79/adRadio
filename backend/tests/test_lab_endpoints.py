"""Tests for /lab/* endpoints."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.api.deps import get_current_user
from app.database import get_db


@pytest.fixture
def client(test_user):
    async def _fake_user():
        return test_user

    async def _fake_db():
        db = AsyncMock()
        yield db

    main_module.app.dependency_overrides[get_current_user] = _fake_user
    main_module.app.dependency_overrides[get_db] = _fake_db
    yield TestClient(main_module.app)
    main_module.app.dependency_overrides.clear()


class TestStartLabRun:
    def test_creates_run_and_queues_task(self, client, test_user):
        with patch("app.workers.tasks.run_lab_task") as mock_task:
            mock_task.apply_async = MagicMock()
            r = client.post("/api/v1/lab/run")
        assert r.status_code == 202
        data = r.json()
        assert data["status"] == "running"
        assert data["id"]
        mock_task.apply_async.assert_called_once()
        assert mock_task.apply_async.call_args.kwargs["queue"] == "processing"


class TestListLabRuns:
    def test_returns_only_current_user_runs(self, client, test_user):
        row = MagicMock(
            id=uuid.uuid4(), status="completed", overall_score=82,
            error_message=None, created_at=MagicMock(), completed_at=MagicMock(),
        )
        # Pydantic will need real datetimes — patch with actual values.
        from datetime import datetime, timezone
        row.created_at = datetime.now(timezone.utc)
        row.completed_at = datetime.now(timezone.utc)

        with patch("app.database.get_db"):
            pass  # db is overridden via fixture

        async def _fake_db_with_result():
            db = AsyncMock()
            result = MagicMock()
            result.scalars.return_value.all.return_value = [row]
            db.execute.return_value = result
            yield db

        main_module.app.dependency_overrides[get_db] = _fake_db_with_result
        r = client.get("/api/v1/lab/runs")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["overall_score"] == 82


class TestGetLabRun:
    def test_invalid_uuid_returns_404(self, client):
        r = client.get("/api/v1/lab/runs/not-a-uuid")
        assert r.status_code == 404

    def test_not_found_returns_404(self, client):
        async def _fake_db_none():
            db = AsyncMock()
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            db.execute.return_value = result
            yield db

        main_module.app.dependency_overrides[get_db] = _fake_db_none
        r = client.get(f"/api/v1/lab/runs/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_found_returns_details_with_conversations(self, client, test_user):
        from datetime import datetime, timezone

        run_id = uuid.uuid4()
        conv = MagicMock(
            id=uuid.uuid4(), persona_key="comprador_decidido", persona_label="El comprador decidido",
            transcript=[{"role": "user", "content": "hola"}], score=90,
            findings=[{"type": "otro", "severity": "baja", "evidence": "x", "suggestion": "y"}],
        )
        lab_run = MagicMock(
            id=run_id, status="completed", overall_score=90, error_message=None,
            created_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
            conversations=[conv],
        )

        async def _fake_db_found():
            db = AsyncMock()
            result = MagicMock()
            result.scalar_one_or_none.return_value = lab_run
            db.execute.return_value = result
            yield db

        main_module.app.dependency_overrides[get_db] = _fake_db_found
        r = client.get(f"/api/v1/lab/runs/{run_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["overall_score"] == 90
        assert len(data["conversations"]) == 1
        assert data["conversations"][0]["persona_key"] == "comprador_decidido"
