"""
WhatsApp Cloud API connection — self-service "paste credentials, test, save"
flow (replaces manual Twilio console setup). Mirrors vocero-crm's
GET/PUT/POST(test) shape: the test endpoint never persists, PUT always
re-validates server-side before saving.
"""
import logging

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
