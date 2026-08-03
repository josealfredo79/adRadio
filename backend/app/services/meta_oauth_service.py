"""
Embedded Signup (OAuth "Conectar con Meta") — server-side half.

The Facebook JS SDK opens Meta's signup flow in the customer's browser; on
success it hands us an authorization `code` plus the WABA ID and phone number
ID the customer picked. This service exchanges that code for a long-lived
business token and verifies the number, so the advertiser never has to
generate or paste a token by hand.
"""
import logging
from dataclasses import dataclass

import httpx

from app.config import settings
from app.services.meta_client import MetaApiError

logger = logging.getLogger(__name__)


@dataclass
class OAuthResult:
    ok: bool
    token: str | None = None
    display_phone_number: str | None = None
    verified_name: str | None = None
    code: str | None = None
    message: str | None = None


async def exchange_embedded_code(code: str, waba_id: str, phone_number_id: str) -> OAuthResult:
    """Exchange the one-time Embedded Signup code for a customer business token."""
    if not settings.META_APP_ID or not settings.META_APP_SECRET:
        return OAuthResult(
            ok=False,
            code="missing_config",
            message="META_APP_ID / META_APP_SECRET no están configurados en el servidor",
        )

    url = f"{settings.META_GRAPH_BASE_URL}/{settings.META_GRAPH_API_VERSION}/oauth/access_token"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                url,
                params={
                    "client_id": settings.META_APP_ID,
                    "client_secret": settings.META_APP_SECRET,
                    "code": code,
                },
            )
    except httpx.RequestError as e:
        return OAuthResult(ok=False, code="meta_unavailable", message=f"No se pudo conectar con Meta: {e}")

    try:
        data = resp.json()
    except Exception:
        data = {}

    if resp.is_error or "access_token" not in data:
        err = data.get("error", {}) if isinstance(data, dict) else {}
        logger.warning("[META OAUTH] code exchange failed: %s", err)
        return OAuthResult(
            ok=False,
            code="exchange_failed",
            message=err.get("message", "Meta rechazó el código de autorización"),
        )

    token = data["access_token"]

    # Verify the token actually owns the chosen number (also fetches display name).
    try:
        from app.services.meta_connect_service import test_connection
        check = await test_connection(phone_number_id, token)
    except MetaApiError as e:
        return OAuthResult(ok=False, code="meta_error", message=str(e))

    if not check.ok:
        return OAuthResult(
            ok=False,
            code=check.code or "meta_error",
            message=check.message or "No se pudo validar el número con Meta",
        )

    return OAuthResult(
        ok=True,
        token=token,
        display_phone_number=check.display_phone_number,
        verified_name=check.verified_name,
    )
