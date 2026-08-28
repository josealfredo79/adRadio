"""
Provisioning steps the server runs on the advertiser's OWN Meta App via the
Graph API, so the self-service manual onboarding needs fewer clicks in the
Meta UI.

Fase A (this module today): `configure_app_webhook` — point the advertiser's
app at IaRadio's webhook so inbound messages actually arrive. Without this, a
manually-connected advertiser can send but never receive (their app isn't
wired to our central webhook — see meta_incoming.py).

Fase B/C (later): number verification (request_code/verify_code/register) and
template creation land here too.
"""
import logging
from dataclasses import dataclass, field
from typing import Literal

from app.config import settings
from app.services.meta_client import MetaApiError, graph_request

logger = logging.getLogger(__name__)

ProvisionErrorCode = Literal["invalid_credentials", "meta_unavailable", "meta_error"]

# Webhook fields the advertiser's app must be subscribed to for IaRadio to
# receive everything meta_incoming.py handles.
WEBHOOK_FIELDS = "messages,message_template_status_update,phone_number_quality_update,account_alerts"


@dataclass
class ProvisionResult:
    ok: bool
    code: ProvisionErrorCode | None = None
    message: str | None = None
    data: dict = field(default_factory=dict)


def _webhook_callback_url() -> str:
    return f"{settings.BASE_URL.rstrip('/')}/api/v1/webhooks/meta"


def _map_error(e: MetaApiError) -> ProvisionResult:
    if e.is_auth_error:
        return ProvisionResult(
            ok=False,
            code="invalid_credentials",
            message="Meta rechazó el App ID / App Secret. Verifica que sean de la misma app y estén bien copiados.",
        )
    if e.status == 0 or e.status >= 500:
        return ProvisionResult(
            ok=False,
            code="meta_unavailable",
            message="Meta no está disponible en este momento; intenta de nuevo",
        )
    return ProvisionResult(ok=False, code="meta_error", message=str(e))


async def configure_app_webhook(app_id: str, app_secret: str) -> ProvisionResult:
    """Subscribe the advertiser's app to WhatsApp webhooks pointing at IaRadio.

    `POST /{app_id}/subscriptions` with the app access token `{app_id}|{app_secret}`.
    Idempotent — Meta upserts the callback URL / fields on repeat calls.
    """
    app_access_token = f"{app_id}|{app_secret}"
    try:
        data = await graph_request(
            f"{app_id}/subscriptions",
            token=app_access_token,
            method="POST",
            params={
                "object": "whatsapp_business_account",
                "callback_url": _webhook_callback_url(),
                "verify_token": settings.META_WEBHOOK_VERIFY_TOKEN,
                "fields": WEBHOOK_FIELDS,
            },
        )
    except MetaApiError as e:
        logger.warning("[META PROVISION] configure_app_webhook failed app=%s: %s", app_id, e)
        return _map_error(e)

    if not data.get("success", True):
        return ProvisionResult(
            ok=False,
            code="meta_error",
            message="Meta no confirmó la suscripción del webhook",
            data=data,
        )
    return ProvisionResult(ok=True, data=data)
