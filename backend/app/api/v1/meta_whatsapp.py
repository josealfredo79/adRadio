"""
WhatsApp Cloud API connection — self-service "paste credentials, test, save"
flow (replaces manual Twilio console setup). Mirrors vocero-crm's
GET/PUT/POST(test) shape: the test endpoint never persists, PUT always
re-validates server-side before saving.
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.core.crypto import encrypt_secret
from app.database import get_db
from app.models.user import User
from app.schemas.meta_whatsapp import (
    MetaWhatsappConnectionOut,
    MetaWhatsappCredentials,
    MetaWhatsappHealthOut,
    MetaWhatsappTestResult,
)
from app.services.meta_connect_service import subscribe_app_to_waba, test_connection
from app.services.meta_oauth_service import exchange_embedded_code
from app.services.meta_provisioning import configure_app_webhook

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta-whatsapp"])


def _connection_out(user: User, *, webhook_message: str | None = None) -> MetaWhatsappConnectionOut:
    """Build the connection snapshot returned by every /me/whatsapp-connection*
    endpoint. `webhook_message` carries a transient note from the write that
    just ran (e.g. why the app webhook config failed)."""
    from app.core.crypto import EncryptedValue, decrypt_secret

    token_last4 = None
    if user.meta_token_cipher:
        try:
            token = decrypt_secret(EncryptedValue(
                cipher=user.meta_token_cipher, iv=user.meta_token_iv, tag=user.meta_token_tag,
            ))
            token_last4 = token[-4:] if len(token) >= 4 else token
        except Exception:
            token_last4 = None

    return MetaWhatsappConnectionOut(
        waba_id=user.meta_waba_id,
        phone_number_id=user.meta_phone_number_id,
        display_phone_number=user.meta_display_phone_number,
        verified_name=user.meta_verified_name,
        status=user.meta_connection_status,
        token_last4=token_last4,
        utility_template_status=user.meta_utility_template_status,
        utility_template_name=user.meta_utility_template_name,
        appointment_template_name=user.meta_appointment_template_name,
        radio_invite_template_name=user.meta_radio_invite_template_name,
        app_id_last4=(user.meta_app_id[-4:] if user.meta_app_id else None),
        app_secret_set=bool(user.meta_app_secret_cipher),
        webhook_configured=bool(user.meta_webhook_configured),
        webhook_message=webhook_message,
        verification_status=user.meta_verification_status,
    )


@router.get("/me/whatsapp-connection", response_model=MetaWhatsappConnectionOut)
async def get_whatsapp_connection(current_user: User = Depends(get_current_user)):
    return _connection_out(current_user)


@router.get("/me/whatsapp-health", response_model=MetaWhatsappHealthOut)
async def get_whatsapp_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Capa 15 anti-baneo: snapshot de todo lo que las capas 6-14 vienen
    calculando en segundo plano (rating, tier, warm-up, tope efectivo de
    destinatarios, campañas activas/pausadas) para que el advertiser no
    tenga que adivinar por qué sus campañas dejaron de enviarse."""
    from sqlalchemy import func, select

    from app.models.campaign import Campaign
    from app.models.message import Message
    from app.services.meta_quality_service import (
        resolve_tier_limit, resolve_warmup_cap, warmup_days_remaining,
    )
    from app.workers.task_helpers.campaign_ops import get_recipient_cap_state

    tier_limit = resolve_tier_limit(current_user.meta_messaging_tier)
    warmup_cap = resolve_warmup_cap(current_user.meta_connected_at)
    cap_state = await get_recipient_cap_state(db, current_user)

    # Meta error 131042 = business-eligibility / payment-method problem on the
    # WABA — templates (any business-initiated message) stop going out entirely
    # until a payment method is added. It's an account-config gap Meta never
    # surfaces in-app, so mirror the last 7 days of failed sends carrying it.
    billing_error_last_seen = (
        await db.execute(
            select(func.max(Message.created_at)).where(
                Message.advertiser_id == current_user.id,
                Message.error_code.ilike("%131042%"),
                Message.created_at >= datetime.now(timezone.utc) - timedelta(days=7),
            )
        )
    ).scalar_one_or_none()

    counts_result = await db.execute(
        select(Campaign.status, func.count()).where(
            Campaign.advertiser_id == current_user.id,
            Campaign.status.in_(("scheduled", "running", "paused")),
        ).group_by(Campaign.status)
    )
    counts = dict(counts_result.all())
    active_count = counts.get("scheduled", 0) + counts.get("running", 0)
    paused_count = counts.get("paused", 0)

    return MetaWhatsappHealthOut(
        quality_rating=current_user.meta_quality_rating,
        messaging_tier=current_user.meta_messaging_tier,
        tier_recipient_limit=tier_limit,
        send_throttle_per_hour=current_user.meta_send_throttle_per_hour,
        connected_at=current_user.meta_connected_at.isoformat() if current_user.meta_connected_at else None,
        warmup_active=warmup_cap is not None,
        warmup_recipient_cap=warmup_cap,
        warmup_days_remaining=warmup_days_remaining(current_user.meta_connected_at),
        recipients_sent_last_24h=cap_state.count,
        effective_recipient_limit=cap_state.limit,
        active_campaigns_count=active_count,
        paused_campaigns_count=paused_count,
        billing_error_recent=billing_error_last_seen is not None,
        billing_error_last_seen=billing_error_last_seen.isoformat() if billing_error_last_seen else None,
    )


@router.post("/me/whatsapp-connection/test", response_model=MetaWhatsappTestResult)
async def test_whatsapp_connection(
    body: MetaWhatsappCredentials,
    current_user: User = Depends(get_current_user),
):
    """Validate token<->phone_number_id against the Graph API. Never persists.
    Requires auth even though nothing is written — otherwise this endpoint
    would be an open proxy for probing arbitrary Meta credentials."""
    check = await test_connection(body.phone_number_id, body.token)
    if not check.ok:
        status_code = 503 if check.code == "meta_unavailable" else 422
        raise HTTPException(status_code=status_code, detail=check.message)
    return MetaWhatsappTestResult(
        ok=check.ok,
        display_phone_number=check.display_phone_number,
        verified_name=check.verified_name,
        code=check.code,
        message=check.message,
    )


class MetaEmbeddedConfigOut(BaseModel):
    app_id: str
    config_id: str
    enabled: bool


@router.get("/me/whatsapp-embedded-config", response_model=MetaEmbeddedConfigOut)
async def get_whatsapp_embedded_config(current_user: User = Depends(get_current_user)):
    """Expose whether one-click "Conectar con Meta" is wired up server-side.
    App ID / config ID are public (they ship inside the FB JS SDK anyway).
    `enabled` also requires the explicit META_EMBEDDED_SIGNUP_ENABLED switch —
    the config can sit loaded in prod with the button still hidden until Meta
    approves TP/BSP (see meta_oauth_service docstring / migration notes)."""
    enabled = bool(
        settings.META_APP_ID
        and settings.META_EMBEDDED_SIGNUP_CONFIG_ID
        and settings.META_EMBEDDED_SIGNUP_ENABLED
    )
    return MetaEmbeddedConfigOut(
        app_id=settings.META_APP_ID,
        config_id=settings.META_EMBEDDED_SIGNUP_CONFIG_ID,
        enabled=enabled,
    )


class MetaEmbeddedSignupBody(BaseModel):
    """Payload from the "Conectar con Meta" flow: the OAuth code plus the
    WABA/phone the customer picked in Meta's own signup window."""
    code: str
    waba_id: str
    phone_number_id: str


@router.post("/me/whatsapp-connection/embedded", response_model=MetaWhatsappConnectionOut)
async def connect_whatsapp_embedded(
    body: MetaEmbeddedSignupBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """One-click "Conectar con Meta" (Embedded Signup). Exchanges the code
    server-side, persists the resulting long-lived token, and subscribes the
    webhook — the advertiser never touches a token."""
    result = await exchange_embedded_code(body.code, body.waba_id, body.phone_number_id)
    if not result.ok or not result.token:
        status_code = 503 if result.code == "meta_unavailable" else 422
        raise HTTPException(status_code=status_code, detail=result.message)

    enc = encrypt_secret(result.token)
    current_user.meta_waba_id = body.waba_id
    current_user.meta_phone_number_id = body.phone_number_id
    current_user.meta_display_phone_number = result.display_phone_number
    current_user.meta_verified_name = result.verified_name
    current_user.meta_token_cipher = enc.cipher
    current_user.meta_token_iv = enc.iv
    current_user.meta_token_tag = enc.tag
    current_user.meta_connection_status = "connected"
    current_user.meta_connected_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(current_user)

    await subscribe_app_to_waba(body.waba_id, result.token)

    return _connection_out(current_user)


@router.put("/me/whatsapp-connection", response_model=MetaWhatsappConnectionOut)
async def save_whatsapp_connection(
    body: MetaWhatsappCredentials,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-validate server-side (never trust a client-reported 'it works'), then persist."""
    check = await test_connection(body.phone_number_id, body.token)
    if not check.ok:
        status_code = 503 if check.code == "meta_unavailable" else 422
        raise HTTPException(status_code=status_code, detail=check.message)

    # Capa 11: reiniciar la rampa de warm-up solo si es un número distinto al
    # que ya estaba conectado (incluye la primera conexión, donde no había
    # ninguno). Ojo: NO usar "meta_connected_at is None" como condición extra
    # — eso dispararía en cualquier resave (ej. refrescar un token vencido)
    # de una cuenta ya conectada desde antes de que existiera esta columna,
    # reiniciando de la nada la rampa de un número que ya lleva meses sano.
    is_new_number = current_user.meta_phone_number_id != body.phone_number_id
    if is_new_number:
        current_user.meta_connected_at = datetime.now(timezone.utc)

    enc = encrypt_secret(body.token)
    current_user.meta_waba_id = body.waba_id
    current_user.meta_phone_number_id = body.phone_number_id
    current_user.meta_display_phone_number = check.display_phone_number
    current_user.meta_verified_name = check.verified_name
    current_user.meta_token_cipher = enc.cipher
    current_user.meta_token_iv = enc.iv
    current_user.meta_token_tag = enc.tag

    # Onboarding manual self-service: si el anunciante trae su propia Meta App,
    # guardamos el App Secret (cifrado) y configuramos el webhook de esa app
    # por Graph API — sin esto, la app del anunciante no está conectada a
    # nuestro webhook central y los mensajes entrantes nunca llegan.
    webhook_message: str | None = None
    if body.app_id and body.app_secret:
        current_user.meta_app_id = body.app_id
        sec = encrypt_secret(body.app_secret)
        current_user.meta_app_secret_cipher = sec.cipher
        current_user.meta_app_secret_iv = sec.iv
        current_user.meta_app_secret_tag = sec.tag

        prov = await configure_app_webhook(body.app_id, body.app_secret)
        current_user.meta_webhook_configured = prov.ok
        if not prov.ok:
            webhook_message = (
                f"Credenciales guardadas, pero no se pudo configurar el webhook automáticamente: "
                f"{prov.message}. Configúralo a mano en tu Meta App → WhatsApp → Configuration "
                f"(Callback URL: {settings.BASE_URL.rstrip('/')}/api/v1/webhooks/meta)."
            )

    # Con App propia: el número ya se validó contra Meta (test_connection ok
    # arriba), así que el único bloqueante de Fase A es el webhook. Si quedó
    # configurado → 'connected'; si falló → 'pending_setup' hasta arreglarlo.
    # Sin App propia (Embedded Signup o número ya 100% en Cloud API) se
    # mantiene el flujo actual.
    if body.app_id and body.app_secret:
        current_user.meta_connection_status = (
            "connected" if current_user.meta_webhook_configured else "pending_setup"
        )
    else:
        current_user.meta_connection_status = "connected"

    await db.commit()
    await db.refresh(current_user)

    await subscribe_app_to_waba(body.waba_id, body.token)

    return _connection_out(current_user, webhook_message=webhook_message)


class MetaTemplatesUpdate(BaseModel):
    utility_template_name: str | None = None
    appointment_template_name: str | None = None
    radio_invite_template_name: str | None = None


@router.patch("/me/whatsapp-templates", response_model=MetaWhatsappConnectionOut)
async def update_whatsapp_templates(
    body: MetaTemplatesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record the name of an already-approved Meta template (created and
    approved directly in WhatsApp Manager — this app doesn't create/submit
    templates yet, see Fase 1 §6 in the migration plan).
    """
    if body.utility_template_name is not None:
        name = body.utility_template_name.strip()
        current_user.meta_utility_template_name = name or None
        current_user.meta_utility_template_status = "approved" if name else "not_configured"
    if body.appointment_template_name is not None:
        current_user.meta_appointment_template_name = body.appointment_template_name.strip() or None
    if body.radio_invite_template_name is not None:
        current_user.meta_radio_invite_template_name = body.radio_invite_template_name.strip() or None
    await db.commit()
    await db.refresh(current_user)
    return _connection_out(current_user)
