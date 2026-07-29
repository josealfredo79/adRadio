"""Tests for GET /conversations/events (SSE stream)."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.api.deps import get_current_user_sse


@pytest.fixture
def client(test_user):
    async def _fake_user():
        return test_user

    main_module.app.dependency_overrides[get_current_user_sse] = _fake_user
    yield TestClient(main_module.app)
    main_module.app.dependency_overrides.clear()


class TestConversationEventsRoute:
    def test_no_redis_yields_unavailable_comment_and_closes(self, client):
        with patch("app.api.v1.conversations.get_redis_optional", new=AsyncMock(return_value=None)):
            with client.stream("GET", "/api/v1/conversations/events") as r:
                assert r.status_code == 200
                assert r.headers["content-type"].startswith("text/event-stream")
                body = b"".join(r.iter_bytes()).decode()
        assert "redis unavailable" in body

    def test_streams_published_event_as_sse_data(self, client):
        pubsub = AsyncMock()
        event_payload = json.dumps({"type": "message", "conversation_id": "c1"})
        # First get_message call returns a real event, second raises to break the loop
        # (simulates the client disconnecting / stream ending for the test).
        pubsub.get_message = AsyncMock(side_effect=[
            {"type": "message", "data": event_payload},
            Exception("client disconnected"),
        ])
        redis = MagicMock()
        redis.pubsub.return_value = pubsub

        with patch("app.api.v1.conversations.get_redis_optional", new=AsyncMock(return_value=redis)):
            with client.stream("GET", "/api/v1/conversations/events") as r:
                assert r.status_code == 200
                body = b"".join(r.iter_bytes()).decode()

        assert f"data: {event_payload}" in body
        pubsub.subscribe.assert_called_once()
        pubsub.unsubscribe.assert_called_once()

    def test_heartbeat_ping_on_timeout(self, client):
        pubsub = AsyncMock()
        pubsub.get_message = AsyncMock(side_effect=[None, Exception("stop")])
        redis = MagicMock()
        redis.pubsub.return_value = pubsub

        with patch("app.api.v1.conversations.get_redis_optional", new=AsyncMock(return_value=redis)):
            with client.stream("GET", "/api/v1/conversations/events") as r:
                body = b"".join(r.iter_bytes()).decode()

        assert ": ping" in body
