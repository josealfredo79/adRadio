"""
Redis pub/sub for the real-time inbox (SSE). Publishing is always
best-effort — a Redis hiccup must never break message processing.
"""
import json
import logging
import uuid

from app.core.redis import get_redis_optional

logger = logging.getLogger(__name__)


def conversation_channel(advertiser_id: uuid.UUID | str) -> str:
    return f"conv_events:{advertiser_id}"


async def publish_conversation_event(advertiser_id: uuid.UUID | str, event: dict) -> None:
    try:
        redis = await get_redis_optional()
        if not redis:
            return
        await redis.publish(conversation_channel(advertiser_id), json.dumps(event))
    except Exception as e:
        logger.warning("[REALTIME] Failed to publish event for advertiser=%s: %s", advertiser_id, e)
