"""
Thin WhatsApp Cloud API (Graph API) HTTP client.

Port of vocero-crm's src/lib/meta/client.ts.
"""
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class MetaApiError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status: int,
        code: int | None = None,
        error_type: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.error_type = error_type
        self.details = details

    @property
    def is_auth_error(self) -> bool:
        return self.status == 401 or self.code == 190 or self.error_type == "OAuthException"


async def graph_request(
    path: str,
    *,
    token: str,
    method: str = "GET",
    body: dict | None = None,
    params: dict | None = None,
) -> dict:
    """Call `{META_GRAPH_BASE_URL}/{META_GRAPH_API_VERSION}/{path}` with a Bearer token.

    `params` are URL query params (Meta accepts POST args as query params too,
    which is how the provisioning endpoints — /subscriptions, /register — expect them).
    """
    url = f"{settings.META_GRAPH_BASE_URL}/{settings.META_GRAPH_API_VERSION}/{path}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.request(method, url, headers=headers, json=body, params=params)
    except httpx.RequestError as e:
        raise MetaApiError(f"No se pudo conectar con Meta: {e}", status=0) from e

    try:
        data = resp.json()
    except Exception:
        data = {}

    if resp.is_error:
        err = data.get("error", {}) if isinstance(data, dict) else {}
        raise MetaApiError(
            err.get("message", f"Meta respondió {resp.status_code}"),
            status=resp.status_code,
            code=err.get("code"),
            error_type=err.get("type"),
            details=err,
        )

    return data


def normalize_recipient(wa_id: str) -> str:
    """Strip the extra '1' from Mexican 521XXXXXXXXXX numbers — outbound send only."""
    clean = wa_id.lstrip("+").replace(" ", "")
    if clean.startswith("521") and len(clean) == 13:
        return "52" + clean[3:]
    return clean


async def download_media(media_id: str, token: str) -> tuple[bytes, str] | None:
    """
    Meta inbound media comes only as a media ID, never a direct URL. Two-step
    resolve: GET /{media_id} (Bearer) returns a short-lived signed `url`,
    which itself must be fetched with the SAME Bearer token — unlike Twilio's
    Basic-Auth-protected but otherwise stable media URLs.
    """
    try:
        meta = await graph_request(media_id, token=token)
    except MetaApiError as e:
        logger.error("[META MEDIA] Failed to resolve media_id=%s: %s", media_id, e)
        return None

    url = meta.get("url")
    if not url:
        logger.error("[META MEDIA] No url in response for media_id=%s", media_id)
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            return resp.content, meta.get("mime_type", "audio/ogg")
    except httpx.HTTPError as e:
        logger.error("[META MEDIA] Failed to download media_id=%s: %s", media_id, e)
        return None
