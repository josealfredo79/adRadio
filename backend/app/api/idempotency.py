"""
Idempotency key middleware for critical POST endpoints.
Uses Redis to store and check Idempotency-Key headers.
"""
import hashlib
import json
import logging
import uuid
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request
from redis.asyncio import Redis as AsyncRedis

from app.core.redis import get_redis_optional


class _JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, uuid.UUID):
            return str(o)
        return super().default(o)

logger = logging.getLogger(__name__)

IDEMPOTENCY_TTL = 3600  # 1 hour


async def check_idempotency(
    request: Request,
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict[str, Any] | None:
    """
    Dependency: if Idempotency-Key header is present and Redis is available,
    returns the cached response if the key was already processed.
    Otherwise returns None and the caller should cache the response after processing.
    """
    idem_key = request.headers.get("Idempotency-Key")
    if not idem_key or not redis:
        return None

    # Namespace the key by the full URL path + idempotency key
    path = request.url.path
    safe_key = hashlib.sha256(f"{path}:{idem_key}".encode()).hexdigest()
    ns_key = f"idempotency:{safe_key}"

    cached = await redis.get(ns_key)
    if cached is not None:
        return json.loads(cached)
    return None


async def store_idempotency_response(
    request: Request,
    redis: AsyncRedis | None,
    response_data: dict[str, Any],
) -> None:
    """Cache a response for an Idempotency-Key so repeated calls return the same result."""
    idem_key = request.headers.get("Idempotency-Key")
    if not idem_key or not redis:
        return

    path = request.url.path
    safe_key = hashlib.sha256(f"{path}:{idem_key}".encode()).hexdigest()
    ns_key = f"idempotency:{safe_key}"

    await redis.setex(ns_key, IDEMPOTENCY_TTL, json.dumps(response_data, cls=_JSONEncoder))


async def idempotent_post(
    request: Request,
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> None:
    """
    Dependency that rejects duplicate POST requests with 409 Conflict
    if the Idempotency-Key has already been processed.
    Use this on endpoints where duplicates are harmful (e.g., sending messages).
    """
    idem_key = request.headers.get("Idempotency-Key")
    if not idem_key or not redis:
        return

    path = request.url.path
    safe_key = hashlib.sha256(f"{path}:{idem_key}".encode()).hexdigest()
    ns_key = f"idempotency:{safe_key}"

    cached = await redis.get(ns_key)
    if cached is not None:
        raise HTTPException(status_code=409, detail="Esta solicitud ya fue procesada (Idempotency-Key duplicada)")
