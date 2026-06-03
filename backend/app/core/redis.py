import logging

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from app.config import settings

logger = logging.getLogger(__name__)

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """
    Retorna una instancia del pool de Redis.
    - Crea el pool una sola vez (singleton).
    - Resetea el pool si la conexión está caída para forzar reconexión.
    - Aumenta timeouts para tolerar la latencia de red en Railway.
    """
    global _redis_pool
    if _redis_pool is not None:
        # Verificar que el pool sigue vivo; si no, forzar recreación
        try:
            await _redis_pool.ping()
        except (RedisConnectionError, RedisTimeoutError, OSError):
            logger.warning("Pool de Redis perdió conexión, reconectando...")
            await close_redis()

    if _redis_pool is None:
        try:
            _redis_pool = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=10,   # 10 s para tolerar latencia Railway
                socket_timeout=10,           # timeout para operaciones (get/set/ping)
                socket_keepalive=True,       # mantiene conexiones vivas en Railway
                retry_on_timeout=True,       # reintenta automáticamente en timeout
                health_check_interval=30,    # Redis-py hace ping interno cada 30 s
            )
            await _redis_pool.ping()
            logger.info("Conexión a Redis establecida correctamente: %s", settings.REDIS_URL)
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
