"""
Cloudflare R2 storage service.
"""
import asyncio
import logging
import boto3  # type: ignore
from botocore.config import Config  # type: ignore

from app.config import settings

logger = logging.getLogger(__name__)

_s3_client = None


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


async def upload_bytes(content: bytes, key: str, content_type: str) -> str | None:
    """Upload bytes to R2. Returns the public URL."""
    if not settings.CF_R2_ACCESS_KEY:
        return None

    def _put():
        client = _get_client()
        client.put_object(
            Bucket=settings.CF_R2_BUCKET,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        return f"{settings.CF_R2_PUBLIC_URL}/{key}"

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _put)
    except Exception as e:
        logger.error("[R2 ERROR] %s", e)
        return None


async def delete_file(key: str) -> bool:
    if not settings.CF_R2_ACCESS_KEY:
        return True

    def _delete():
        client = _get_client()
        client.delete_object(Bucket=settings.CF_R2_BUCKET, Key=key)

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _delete)
        return True
    except Exception as e:
        logger.error("[R2 DELETE ERROR] %s", e)
        return False
