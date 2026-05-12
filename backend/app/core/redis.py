import logging

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from app.config import settings

logger = logging.getLogger(__name__)

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_pool
    try:
        if _redis_pool is None:
            _redis_pool = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=3,
            )
        await _redis_pool.ping()
    except (RedisConnectionError, RedisTimeoutError, OSError) as exc:
        _redis_pool = None
        logger.error("Redis no disponible (%s): %s", settings.REDIS_URL, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio temporalmente no disponible. Intenta de nuevo en unos segundos.",
        ) from exc
    return _redis_pool


async def close_redis():
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
