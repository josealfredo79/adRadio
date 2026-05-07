"""
Campaigns router — /api/v1/campaigns
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.campaign import Campaign
from app.models.user import User
from app.schemas.campaign import (
    CampaignCreate,
    CampaignOut,
    CampaignUpdate,
    GenerateContentRequest,
    GenerateContentResponse,
    GenerateImageRequest,
    GenerateSequenceRequest,
    GenerateSagaRequest,
    GenerateSequenceResponse,
    GenerateRadioAdRequest,
)
from app.services.claude_service import (
    generate_campaign_variants,
    generate_sequence_messages,
    generate_saga_episodes,
)
from app.services.imagen_service import generate_flyer
from app.services.radio_service import generate_radio_ad, generate_radio_script
from app.workers.tasks import schedule_campaign

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Campaign)
        .where(Campaign.advertiser_id == current_user.id)
        .order_by(Campaign.created_at.desc())
    )
    return [CampaignOut.model_validate(c) for c in result.scalars().all()]


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.subscription_status not in ("active", "trial"):
        raise HTTPException(status_code=402, detail="Necesitas un plan activo para crear campañas")

    campaign = Campaign(advertiser_id=current_user.id, **body.model_dump())
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    # If scheduled, dispatch to Celery
    if campaign.schedule.get("start_date") and campaign.status == "scheduled":
        schedule_campaign.delay(str(campaign.id))

    return CampaignOut.model_validate(campaign)


@router.patch("/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.advertiser_id == current_user.id,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(campaign, field, value)

    await db.commit()
    await db.refresh(campaign)
    return CampaignOut.model_validate(campaign)


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.advertiser_id == current_user.id,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    campaign.status = "paused"
    await db.commit()
    return {"message": "Campaña pausada"}


@router.post("/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.advertiser_id == current_user.id,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    campaign.status = "running"
    await db.commit()
    schedule_campaign.delay(str(campaign.id))
    return {"message": "Campaña reanudada"}


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.advertiser_id == current_user.id,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    await db.delete(campaign)
    await db.commit()


@router.get("/{campaign_id}/stats")
async def campaign_stats(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.advertiser_id == current_user.id,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    return campaign.stats


@router.post("/generate-content", response_model=GenerateContentResponse)
async def generate_content(
    body: GenerateContentRequest,
    current_user: User = Depends(get_current_user),
):
    variants = await generate_campaign_variants(
        campaign_type=body.campaign_type,
        business_name=body.business_name,
        intent=body.intent,
    )
    return GenerateContentResponse(variants=variants)


@router.post("/generate-image")
async def generate_image(
    body: GenerateImageRequest,
    current_user: User = Depends(get_current_user),
):
    image_url = await generate_flyer(
        campaign_name=body.campaign_name,
        message_text=body.message_text,
        business_name=body.business_name,
    )
    return {"image_url": image_url}


@router.post("/generate-sequence", response_model=GenerateSequenceResponse)
async def generate_sequence(
    body: GenerateSequenceRequest,
    current_user: User = Depends(get_current_user),
):
    """Genera una secuencia de 3 mensajes para campaña en días distintos."""
    messages = await generate_sequence_messages(
        business_name=body.business_name,
        intent=body.intent,
        campaign_type=body.campaign_type,
    )
    return GenerateSequenceResponse(messages=messages)


@router.post("/generate-saga", response_model=GenerateSequenceResponse)
async def generate_saga(
    body: GenerateSagaRequest,
    current_user: User = Depends(get_current_user),
):
    """Genera 4 episodios de radionovela de marketing para campaña saga."""
    episodes = await generate_saga_episodes(
        business_name=body.business_name,
        product_description=body.product_description,
        protagonist_name=body.protagonist_name,
    )
    return GenerateSequenceResponse(messages=episodes)


@router.post("/generate-radio-ad")
async def generate_radio_ad_endpoint(
    body: GenerateRadioAdRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Genera una cuña publicitaria completa en audio:
    Claude escribe el guión → edge-tts pone voz de locutor → sube a R2.
    Retorna URL del audio .ogg listo para enviar como nota de voz por WhatsApp.
    """
    script = await generate_radio_script(
        business_name=body.business_name,
        message_or_intent=body.intent,
        country=body.country,
        mode=body.mode,
    )
    audio_url = await generate_radio_ad(
        business_name=body.business_name,
        message_or_intent=body.intent,
        country=body.country,
        _script=script,
        mode=body.mode,
    )
    return {"audio_url": audio_url, "script": script}
