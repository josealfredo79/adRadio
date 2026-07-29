"""Tests that mutating conversation endpoints publish a realtime event."""
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


class TestReplyPublishesEvent:
    def test_manual_reply_publishes_message_event(self, client, test_user):
        contact = MagicMock(id=uuid.uuid4(), phone="+521234567890")
        conv = MagicMock(id=uuid.uuid4(), messages=[], contact_id=contact.id)

        async def _fake_db():
            db = AsyncMock()
            result = MagicMock()
            result.first.return_value = (conv, contact)
            db.execute.return_value = result
            db.refresh = AsyncMock(side_effect=lambda m: setattr(m, "id", uuid.uuid4()))
            yield db

        main_module.app.dependency_overrides[get_db] = _fake_db

        with patch("app.services.realtime.publish_conversation_event", new=AsyncMock()) as mock_pub, \
             patch("app.workers.tasks.send_whatsapp_message") as mock_task:
            mock_task.apply_async = MagicMock()
            r = client.post(f"/api/v1/conversations/{conv.id}/reply", json={"text": "Hola, gracias por escribir"})

        assert r.status_code == 200
        mock_pub.assert_called_once_with(test_user.id, {"type": "message", "contact_id": str(contact.id)})


class TestStatusUpdatePublishesEvent:
    def test_escalate_publishes_status_event(self, client, test_user):
        contact_id = uuid.uuid4()
        conv = MagicMock(id=uuid.uuid4(), advertiser_id=test_user.id, status="active", contact_id=contact_id)

        async def _fake_db():
            db = AsyncMock()
            result = MagicMock()
            result.scalar_one_or_none.return_value = conv
            db.execute.return_value = result
            yield db

        main_module.app.dependency_overrides[get_db] = _fake_db

        with patch("app.services.realtime.publish_conversation_event", new=AsyncMock()) as mock_pub:
            r = client.patch(f"/api/v1/conversations/{conv.id}/status", json={"status": "escalated"})

        assert r.status_code == 200
        mock_pub.assert_called_once_with(test_user.id, {"type": "status", "contact_id": str(contact_id)})
