"""
Radio audio proxy — /api/v1/radio
Serves audio files from local storage (primary) or R2 (fallback).
"""
import asyncio
import boto3
import logging
import mimetypes
import os
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/radio", tags=["radio"])

# Local audio storage directory
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static", "audio")


def _ensure_audio_dir():
    os.makedirs(AUDIO_DIR, exist_ok=True)


# Meta's Cloud API validates the Content-Type header against the actual media
# bytes when fetching a `link`-based message — a mismatch (e.g. MP3 bytes
# served as "audio/ogg") can cause it to reject or mangle the media. Every
# TTS provider in this app emits MP3, so the extension-based guess must cover
# it explicitly rather than relying on a single hardcoded default.
_AUDIO_CONTENT_TYPES = {
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".png": "image/png",
}


def _guess_audio_content_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return _AUDIO_CONTENT_TYPES.get(ext) or mimetypes.guess_type(filename)[0] or "audio/mpeg"


def _get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.CF_R2_ENDPOINT,
        aws_access_key_id=settings.CF_R2_ACCESS_KEY,
        aws_secret_access_key=settings.CF_R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _fetch_and_cache_from_r2(filename: str, local_path: str) -> str:
    """Sync helper: fetch audio from R2 and cache to local disk. Returns content type."""
    r2 = _get_r2_client()
    obj = r2.get_object(Bucket=settings.CF_R2_BUCKET, Key=filename)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "wb") as f:
        for chunk in obj["Body"].iter_chunks(chunk_size=65536):
            f.write(chunk)
    return obj.get("ContentType", "audio/ogg")


# Available voices for cuñas de radio
AVAILABLE_VOICES = [
    {"id": "es-MX-JorgeNeural", "name": "Jorge (México)", "lang": "es-MX", "gender": "male", "provider": "edge"},
    {"id": "es-MX-DaliaNeural", "name": "Dalia (México)", "lang": "es-MX", "gender": "female", "provider": "edge"},
    {"id": "es-AR-TomasNeural", "name": "Tomás (Argentina)", "lang": "es-AR", "gender": "male", "provider": "edge"},
    {"id": "es-AR-ElenaNeural", "name": "Elena (Argentina)", "lang": "es-AR", "gender": "female", "provider": "edge"},
    {"id": "es-CO-GonzaloNeural", "name": "Gonzalo (Colombia)", "lang": "es-CO", "gender": "male", "provider": "edge"},
    {"id": "es-CO-SalomeNeural", "name": "Salomé (Colombia)", "lang": "es-CO", "gender": "female", "provider": "edge"},
    {"id": "es-ES-AlvaroNeural", "name": "Álvaro (España)", "lang": "es-ES", "gender": "male", "provider": "edge"},
    {"id": "es-ES-ElviraNeural", "name": "Elvira (España)", "lang": "es-ES", "gender": "female", "provider": "edge"},
]


@router.get("/voices")
@limiter.limit("10/minute")
async def list_voices(request: Request) -> list:
    """List available TTS voices for radio ads."""
    return AVAILABLE_VOICES


@router.get("/audio/{filename:path}")
@limiter.limit("30/minute")
async def serve_audio(request: Request, filename: str) -> FileResponse:
    """Serve an audio file from local storage or R2 fallback."""
    _ensure_audio_dir()

    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid filename")

    local_path = os.path.join(AUDIO_DIR, filename)

    # Try local first
    if os.path.exists(local_path):
        return FileResponse(local_path, media_type=_guess_audio_content_type(filename))

    # Fallback: fetch from R2 and cache locally
    if not settings.CF_R2_ACCESS_KEY:
        raise HTTPException(status_code=404, detail="Audio not found")

    logger.info("Audio not found locally, fetching from R2: %s", filename)
    loop = asyncio.get_event_loop()
    try:
        content_type = await loop.run_in_executor(None, _fetch_and_cache_from_r2, filename, local_path)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail="Audio not found")
        raise HTTPException(status_code=502, detail=f"Storage error: {e.response['Error']['Code']}")

    return FileResponse(local_path, media_type=content_type)
