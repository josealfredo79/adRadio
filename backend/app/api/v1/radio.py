"""
Radio audio proxy — /api/v1/radio
Serves audio files from local storage (primary) or R2 (fallback).
"""
import boto3
import os
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse

from app.config import settings

router = APIRouter(prefix="/radio", tags=["radio"])

# Local audio storage directory
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "audio")


def _ensure_audio_dir():
    os.makedirs(AUDIO_DIR, exist_ok=True)


def _get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.CF_R2_ENDPOINT,
        aws_access_key_id=settings.CF_R2_ACCESS_KEY,
        aws_secret_access_key=settings.CF_R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


@router.get("/audio/{filename:path}")
async def serve_audio(request: Request, filename: str):
    """Serve an audio file from local storage or R2 fallback."""
    _ensure_audio_dir()

    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid filename")

    local_path = os.path.join(AUDIO_DIR, filename)

    # Try local first
    if os.path.exists(local_path):
        return FileResponse(local_path, media_type="audio/ogg")

    # Fallback: fetch from R2 and cache locally
    if not settings.CF_R2_ACCESS_KEY:
        raise HTTPException(status_code=404, detail="Audio not found")

    r2 = _get_r2_client()
    try:
        obj = r2.get_object(Bucket=settings.CF_R2_BUCKET, Key=filename)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail="Audio not found")
        raise HTTPException(status_code=502, detail=f"Storage error: {e.response['Error']['Code']}")

    # Cache to local storage for next time
    with open(local_path, "wb") as f:
        for chunk in obj["Body"].iter_chunks(chunk_size=65536):
            f.write(chunk)

    return FileResponse(local_path, media_type=obj.get("ContentType", "audio/ogg"))
