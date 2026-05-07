"""
Google Imagen 3 — flyer generation service.
Uses a GCP service account (JSON stored in env var) for OAuth2.
"""
import base64
import json

import httpx

from app.config import settings
from app.services.storage_service import upload_bytes


def _get_access_token() -> str | None:
    """Get a short-lived OAuth2 access token from the service account JSON."""
    if not settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        return None
    try:
        from google.oauth2 import service_account  # type: ignore
        import google.auth.transport.requests  # type: ignore

        info = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        request = google.auth.transport.requests.Request()
        creds.refresh(request)
        return creds.token
    except Exception:
        return None


async def generate_flyer(campaign_name: str, message_text: str, business_name: str) -> str | None:
    """
    Generate a promotional flyer using Google Imagen 3.
    Returns the public URL of the uploaded image, or None if not configured.
    """
    token = _get_access_token()
    if not token or not settings.GOOGLE_CLOUD_PROJECT:
        return None

    prompt = (
        f"Professional WhatsApp promotional flyer for '{business_name}'. "
        f"Campaign: {campaign_name}. "
        f"Message: {message_text}. "
        "Clean modern design, vibrant colors, Spanish text, 1:1 aspect ratio."
    )

    endpoint = (
        f"https://us-central1-aiplatform.googleapis.com/v1/projects/"
        f"{settings.GOOGLE_CLOUD_PROJECT}/locations/us-central1/publishers/google/models/"
        f"imagen-3.0-generate-001:predict"
    )

    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": "1:1",
        },
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(endpoint, json=payload, headers=headers)
        if response.status_code != 200:
            return None

        data = response.json()
        b64_image = data["predictions"][0]["bytesBase64Encoded"]
        image_bytes = base64.b64decode(b64_image)

        safe_name = "".join(c if c.isalnum() else "_" for c in campaign_name)[:60]
        return await upload_bytes(image_bytes, f"flyers/{safe_name}.png", "image/png")

