"""Tests for app.services.realtime — pub/sub publishing is always best-effort."""
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.realtime import conversation_channel, publish_conversation_event


class TestConversationChannel:
    def test_channel_name_includes_advertiser_id(self):
        adv_id = uuid.uuid4()
        assert conversation_channel(adv_id) == f"conv_events:{adv_id}"

    def test_channel_name_accepts_string(self):
        assert conversation_channel("abc-123") == "conv_events:abc-123"


class TestPublishConversationEvent:
    @pytest.mark.asyncio
    async def test_publishes_json_to_correct_channel(self):
        redis = AsyncMock()
        adv_id = uuid.uuid4()
        with patch("app.services.realtime.get_redis_optional", new=AsyncMock(return_value=redis)):
            await publish_conversation_event(adv_id, {"type": "message", "conversation_id": "c1"})

        redis.publish.assert_called_once()
        channel, payload = redis.publish.call_args.args
        assert channel == f"conv_events:{adv_id}"
        assert json.loads(payload) == {"type": "message", "conversation_id": "c1"}

    @pytest.mark.asyncio
    async def test_no_redis_is_silent_noop(self):
        with patch("app.services.realtime.get_redis_optional", new=AsyncMock(return_value=None)):
            await publish_conversation_event(uuid.uuid4(), {"type": "message"})  # must not raise

    @pytest.mark.asyncio
    async def test_redis_error_is_swallowed_not_raised(self):
        redis = AsyncMock()
        redis.publish.side_effect = Exception("connection reset")
        with patch("app.services.realtime.get_redis_optional", new=AsyncMock(return_value=redis)):
            await publish_conversation_event(uuid.uuid4(), {"type": "message"})  # must not raise
