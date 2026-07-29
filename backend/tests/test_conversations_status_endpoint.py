"""
Tests for PATCH /conversations/{id}/status.

Regression coverage for a real bug found while auditing the human-handoff
feature: the endpoint's docstring says "Manually escalate or close a
conversation", but its Pydantic body only accepted Literal["active","closed"]
— so `status: "escalated"` (exactly what the "Pausar bot" button in the
inbox sends) was rejected with a 422 before the handler ever ran. The
"Pausar bot" button could never have worked.
"""
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

    main_module.app.dependency_overrides[get_current_user] = _fake_user
    yield TestClient(main_module.app)
    main_module.app.dependency_overrides.clear()


def _db_with_conversation(conv):
    async def _fake_db():
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = conv
        db.execute.return_value = result
        yield db
    return _fake_db


class TestUpdateConversationStatus:
    def test_escalated_is_accepted(self, client, test_user):
        conv = MagicMock(id=uuid.uuid4(), advertiser_id=test_user.id, status="active")
        main_module.app.dependency_overrides[get_db] = _db_with_conversation(conv)

        r = client.patch(f"/api/v1/conversations/{conv.id}/status", json={"status": "escalated"})

        assert r.status_code == 200
        assert conv.status == "escalated"

    def test_active_is_accepted(self, client, test_user):
        conv = MagicMock(id=uuid.uuid4(), advertiser_id=test_user.id, status="escalated")
        main_module.app.dependency_overrides[get_db] = _db_with_conversation(conv)

        r = client.patch(f"/api/v1/conversations/{conv.id}/status", json={"status": "active"})

        assert r.status_code == 200
        assert conv.status == "active"

    def test_closed_is_accepted(self, client, test_user):
        conv = MagicMock(id=uuid.uuid4(), advertiser_id=test_user.id, status="active")
        main_module.app.dependency_overrides[get_db] = _db_with_conversation(conv)

        r = client.patch(f"/api/v1/conversations/{conv.id}/status", json={"status": "closed"})

        assert r.status_code == 200
        assert conv.status == "closed"

    def test_invalid_status_rejected_with_422(self, client, test_user):
        conv_id = uuid.uuid4()
        main_module.app.dependency_overrides[get_db] = _db_with_conversation(MagicMock())

        r = client.patch(f"/api/v1/conversations/{conv_id}/status", json={"status": "banana"})

        assert r.status_code == 422

    def test_conversation_not_found_returns_404(self, client):
        main_module.app.dependency_overrides[get_db] = _db_with_conversation(None)

        r = client.patch(f"/api/v1/conversations/{uuid.uuid4()}/status", json={"status": "escalated"})

        assert r.status_code == 404
