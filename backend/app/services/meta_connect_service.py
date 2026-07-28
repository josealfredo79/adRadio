"""
Test and register a WhatsApp Cloud API connection — no persistence here.

Port of vocero-crm's src/server/whatsapp/connect.ts.
"""
import logging
from dataclasses import dataclass
from typing import Literal

from app.services.meta_client import MetaApiError, graph_request

logger = logging.getLogger(__name__)

ConnectionErrorCode = Literal["invalid_token", "meta_unavailable", "meta_error"]


@dataclass
class ConnectionCheck:
    ok: bool
    display_phone_number: str | None = None
    verified_name: str | None = None
    code: ConnectionErrorCode | None = None
    message: str | None = None


async def test_connection(phone_number_id: str, token: str) -> ConnectionCheck:
    """Validate token<->number against the Graph API without persisting anything."""
    try:
        res = await graph_request(
            f"{phone_number_id}?fields=display_phone_number,verified_name",
            token=token,
        )
    except MetaApiError as e:
        if e.is_auth_error:
            return ConnectionCheck(
                ok=False,
                code="invalid_token",
                message="El token no es válido o expiró. Verifica que corresponde a este número (usuario del sistema con permisos whatsapp_business_messaging y whatsapp_business_management).",
            )
        if e.status == 0 or e.status >= 500:
            return ConnectionCheck(
                ok=False,
                code="meta_unavailable",
                message="Meta no está disponible en este momento; intenta de nuevo",
            )
        return ConnectionCheck(ok=False, code="meta_error", message=str(e))

    display = res.get("display_phone_number")
    if not display:
        return ConnectionCheck(
            ok=False,
            code="meta_error",
            message="Meta no devolvió el número: verifica que el Phone Number ID sea correcto",
        )

    return ConnectionCheck(
        ok=True,
        display_phone_number=display,
        verified_name=res.get("verified_name"),
    )


async def subscribe_app_to_waba(waba_id: str, token: str) -> None:
    """Route this WABA's webhooks to our app. Best-effort — never raises."""
    try:
        await graph_request(f"{waba_id}/subscribed_apps", token=token, method="POST")
    except MetaApiError as e:
        logger.warning("[META] subscribe_app_to_waba failed for waba=%s: %s", waba_id, e)
