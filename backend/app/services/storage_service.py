"""
Cloudflare R2 storage service with local fallback.
Saves files locally first, then uploads to R2 (async).
Returns a URL that serves from the backend.
"""
import asyncio
import logging
import os

import boto3  # type: ignore
from botocore.config import Config  # type: ignore

from app.config import settings

logger = logging.getLogger(__name__)

_s3_client = None

# Local audio storage (served directly by the backend)
_LOCAL_AUDIO_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "audio")


def _get_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.CF_R2_ENDPOINT,
            aws_access_key_id=settings.CF_R2_ACCESS_KEY,
            aws_secret_access_key=settings.CF_R2_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    return _s3_client


def _ensure_local_dir() -> None:
    os.makedirs(_LOCAL_AUDIO_DIR, exist_ok=True)


async def upload_bytes(content: bytes, key: str, content_type: str) -> str | None:
    """Save locally and return a URL through the backend proxy."""
    _ensure_local_dir()

    local_path = os.path.join(_LOCAL_AUDIO_DIR, key)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    def _write() -> None:
        with open(local_path, "wb") as f:
            f.write(content)

    await asyncio.to_thread(_write)

    url = f"{settings.BASE_URL}/api/v1/radio/audio/{key}"
    logger.info("[STORAGE] Saved locally %s bytes → %s", len(content), url)

    # Async upload to R2 (blocking to ensure it saves!)
    if settings.CF_R2_ACCESS_KEY:
        await _upload_to_r2(content, key, content_type)

    return url


async def _upload_to_r2(content: bytes, key: str, content_type: str):
    """Upload to R2 in background. Failures are logged but non-blocking."""
    try:
        def _put():
            client = _get_client()
            client.put_object(
                Bucket=settings.CF_R2_BUCKET,
                Key=key,
                Body=content,
                ContentType=content_type,
            )

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _put)
        logger.info("[R2] Synced %s/%s", settings.CF_R2_BUCKET, key)
    except Exception as e:
        logger.warning("[R2] Sync failed for %s: %s", key, e)





async def read_bytes(url: str) -> bytes | None:
    """Los bytes de un archivo guardado con upload_bytes (local, si no R2) o
    de una URL pública. Para dibujar la foto del producto en una campaña."""
    marker = "/api/v1/radio/audio/"
    if marker in url:
        key = url.split(marker, 1)[1]
        if ".." in key or key.startswith("/"):
            return None
        local_path = os.path.join(_LOCAL_AUDIO_DIR, key)
        if os.path.exists(local_path):
            return await asyncio.to_thread(lambda: open(local_path, "rb").read())
        if settings.CF_R2_ACCESS_KEY:
            try:
                def _get() -> bytes:
                    return _get_client().get_object(Bucket=settings.CF_R2_BUCKET, Key=key)["Body"].read()
                return await asyncio.to_thread(_get)
            except Exception:
                logger.warning("[STORAGE] read failed for %s", key, exc_info=True)
                return None
        return None
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(url)
            res.raise_for_status()
            return res.content
    except Exception:
        logger.warning("[STORAGE] read failed for %s", url, exc_info=True)
        return None
