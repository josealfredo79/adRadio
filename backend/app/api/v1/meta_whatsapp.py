"""
WhatsApp Cloud API connection — self-service "paste credentials, test, save"
flow (replaces manual Twilio console setup). Mirrors vocero-crm's
GET/PUT/POST(test) shape: the test endpoint never persists, PUT always
re-validates server-side before saving.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
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

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meta-whatsapp"])


@router.get("/me/whatsapp-connection", response_model=MetaWhatsappConnectionOut)
async def get_whatsapp_connection(current_user: User = Depends(get_current_user)):
    token_last4 = None
    if current_user.meta_token_cipher:
        try:
            from app.core.crypto import EncryptedValue, decrypt_secret
            token = decrypt_secret(
                EncryptedValue(
                    cipher=current_user.meta_token_cipher,
                    iv=current_user.meta_token_iv,
                    tag=current_user.meta_token_tag,
                )
            )
            token_last4 = token[-4:] if len(token) >= 4 else token
        except Exception:
            token_last4 = None

    return MetaWhatsappConnectionOut(
        waba_id=current_user.meta_waba_id,
        phone_number_id=current_user.meta_phone_number_id,
        display_phone_number=current_user.meta_display_phone_number,
        verified_name=current_user.meta_verified_name,
        status=current_user.meta_connection_status,
        token_last4=token_last4,
        utility_template_status=current_user.meta_utility_template_status,
        utility_template_name=current_user.meta_utility_template_name,
        appointment_template_name=current_user.meta_appointment_template_name,
    )


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
    from app.services.meta_quality_service import (
        resolve_tier_limit, resolve_warmup_cap, warmup_days_remaining,
    )
    from app.workers.task_helpers.campaign_ops import get_recipient_cap_state

    tier_limit = resolve_tier_limit(current_user.meta_messaging_tier)
    warmup_cap = resolve_warmup_cap(current_user.meta_connected_at)
    cap_state = await get_recipient_cap_state(db, current_user)

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
    current_user.meta_connection_status = "connected"
    await db.commit()
    await db.refresh(current_user)

    await subscribe_app_to_waba(body.waba_id, body.token)

    return await get_whatsapp_connection(current_user)


class MetaTemplatesUpdate(BaseModel):
    utility_template_name: str | None = None
    appointment_template_name: str | None = None


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
    await db.commit()
    await db.refresh(current_user)
    return await get_whatsapp_connection(current_user)
