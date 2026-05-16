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


def _ensure_local_dir():
    os.makedirs(_LOCAL_AUDIO_DIR, exist_ok=True)


async def upload_bytes(content: bytes, key: str, content_type: str) -> str | None:
    """Save locally and return a URL through the backend proxy."""
    _ensure_local_dir()

    local_path = os.path.join(_LOCAL_AUDIO_DIR, key)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(content)

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



