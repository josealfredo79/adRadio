"""
Shared rate limiter instance — built once, used by main.py and individual routers.
"""
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

logger = logging.getLogger(__name__)


def _build_limiter() -> Limiter:
    storage_uri = settings.REDIS_URL
    if not settings.DEBUG:
        try:
            import redis as sync_redis  # type: ignore
            r = sync_redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
            r.ping()
            r.close()
            logger.info("[RateLimit] Backend: Redis (%s)", settings.REDIS_URL)
        except Exception as e:
            logger.critical("[RateLimit] Redis no disponible en producción: %s", e)
            raise RuntimeError("Redis is required for rate limiting in production") from e
    else:
        try:
            import redis as sync_redis
            r = sync_redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
            r.ping()
            r.close()
            logger.info("[RateLimit] Backend: Redis (%s)", settings.REDIS_URL)
        except Exception:
            storage_uri = "memory://"
            logger.warning(
                "[RateLimit] Redis no disponible al arrancar — usando memoria local. "
                "El límite NO será global entre múltiples workers."
            )
    return Limiter(
        key_func=get_remote_address,
        storage_uri=storage_uri,
        default_limits=["200/minute"],
    )


limiter = _build_limiter()
