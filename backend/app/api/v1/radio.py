"""
Radio audio proxy — /api/v1/radio
Serves R2-stored audio files publicly so Twilio can download them.
"""
import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.config import settings

router = APIRouter(prefix="/radio", tags=["radio"])


def _get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.CF_R2_ENDPOINT,
        aws_access_key_id=settings.CF_R2_ACCESS_KEY,
        aws_secret_access_key=settings.CF_R2_SECRET_KEY,
        region_name="auto",
    )


@router.get("/audio/{key:path}")
async def serve_audio(request: Request, key: str):
    """Proxy an audio file from R2 so Twilio/WhatsApp can download it."""
    if not settings.CF_R2_ACCESS_KEY:
        raise HTTPException(status_code=503, detail="R2 not configured")

    if ".." in key:
        raise HTTPException(status_code=400, detail="Invalid key")

    r2 = _get_r2_client()
    try:
        obj = r2.get_object(Bucket=settings.CF_R2_BUCKET, Key=key)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise HTTPException(status_code=404, detail="Audio not found")
        raise HTTPException(status_code=502, detail="Storage error")

    content_type = obj.get("ContentType", "audio/ogg")

    def stream():
        for chunk in obj["Body"].iter_chunks(chunk_size=65536):
            yield chunk

    return StreamingResponse(
        stream(),
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
