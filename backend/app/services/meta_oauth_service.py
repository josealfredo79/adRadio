"""
Embedded Signup (OAuth "Conectar con Meta") — server-side half.

The Facebook JS SDK opens Meta's signup flow in the customer's browser; on
success it hands us an authorization `code` plus the WABA ID and phone number
ID the customer picked. This service exchanges that code for a long-lived
business token and verifies the number, so the advertiser never has to
generate or paste a token by hand.

The SDK's sessionInfo message (with the WABA/phone IDs) doesn't always arrive,
and a customer can finish with a WABA but no number (FINISH_ONLY_WABA); in
those cases the IDs are looked up from the token itself.
"""
import logging
from dataclasses import dataclass

import httpx

from app.config import settings
from app.services.meta_client import MetaApiError, graph_request

logger = logging.getLogger(__name__)


@dataclass
class OAuthResult:
    ok: bool
    token: str | None = None
    waba_id: str | None = None
    phone_number_id: str | None = None
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

    try:
        waba_id = waba_id or await _granted_waba_id(token)
        if not waba_id:
            return OAuthResult(
                ok=False,
                code="no_waba",
                message="Meta no compartió ninguna cuenta de WhatsApp Business (o compartió varias). Intenta de nuevo eligiendo una sola.",
            )
        phone_number_id = phone_number_id or await _only_phone_number_id(waba_id, token)
        if not phone_number_id:
            return OAuthResult(
                ok=False,
                code="no_phone",
                message="Tu cuenta de WhatsApp Business quedó conectada pero sin un número (o con varios). Vuelve a conectar y elige un solo número.",
            )
    except MetaApiError as e:
        logger.warning("[META OAUTH] could not resolve WABA/phone from token: %s", e)
        return OAuthResult(ok=False, code="meta_error", message=str(e))

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
        waba_id=waba_id,
        phone_number_id=phone_number_id,
        display_phone_number=check.display_phone_number,
        verified_name=check.verified_name,
    )


async def _granted_waba_id(token: str) -> str | None:
    """The single WABA the customer shared with our app, read from the
    token's granular scopes. None if there are zero or several."""
    data = await graph_request(
        "debug_token",
        token=f"{settings.META_APP_ID}|{settings.META_APP_SECRET}",
        params={"input_token": token},
    )
    ids: set[str] = set()
    for scope in (data.get("data") or {}).get("granular_scopes") or []:
        if scope.get("scope") == "whatsapp_business_management":
            ids.update(str(t) for t in scope.get("target_ids") or [])
    return ids.pop() if len(ids) == 1 else None


async def _only_phone_number_id(waba_id: str, token: str) -> str | None:
    """The WABA's phone number ID when it has exactly one."""
    data = await graph_request(f"{waba_id}/phone_numbers", token=token, params={"fields": "id"})
    numbers = data.get("data") or []
    return str(numbers[0]["id"]) if len(numbers) == 1 else None
