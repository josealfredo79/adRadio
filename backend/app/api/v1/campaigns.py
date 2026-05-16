"""
Campaigns router — /api/v1/campaigns
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    ParrillaRequest,
    ParrillaOut,
    ParrillaDayOut,
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
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Campaign)
        .where(Campaign.advertiser_id == current_user.id)
        .order_by(Campaign.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
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

    # If scheduled, dispatch to Celery respecting the start_date
    if campaign.schedule.get("start_date") and campaign.status == "scheduled":
        from datetime import datetime, timezone
        try:
            start_dt = datetime.fromisoformat(
                campaign.schedule["start_date"].replace("Z", "+00:00")
            )
            countdown = max(0, int((start_dt - datetime.now(timezone.utc)).total_seconds()))
        except (ValueError, KeyError):
            countdown = 0
        schedule_campaign.apply_async(args=[str(campaign.id)], countdown=countdown)

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
        business_category=body.business_category,
        extra_context=body.extra_context,
    )
    audio_url = await generate_radio_ad(
        business_name=body.business_name,
        message_or_intent=body.intent,
        country=body.country,
        _script=script,
        mode=body.mode,
        business_category=body.business_category,
    )
    return {"audio_url": audio_url, "script": script}


# ─── Modos por día según el plan ──────────────────────────────────────────────
# Orden estratégico: valor primero, oferta al final de semana
_PARRILLA_ALL = [
    (0, "Lunes",     "comunitaria", "🌿"),
    (1, "Martes",    "capsula",     "💡"),
    (2, "Miércoles", "trivia",      "🧠"),
    (3, "Jueves",    "historia",    "📖"),
    (4, "Viernes",   "classic",     "🎙️"),
    (5, "Sábado",    "alerta",      "🚨"),
    (6, "Domingo",   "estacional",  "🗓️"),
]

# Starter solo accede a los primeros 4 días con classic
_PARRILLA_STARTER = [
    (0, "Lunes",     "classic", "🎙️"),
    (1, "Martes",    "classic", "🎙️"),
    (2, "Miércoles", "classic", "🎙️"),
    (3, "Jueves",    "classic", "🎙️"),
    (4, "Viernes",   "classic", "🎙️"),
    (5, "Sábado",    "classic", "🎙️"),
    (6, "Domingo",   "classic", "🎙️"),
]

# Growth: 4 modos (sin alerta ni estacional)
_PARRILLA_GROWTH = [
    (0, "Lunes",     "comunitaria", "🌿"),
    (1, "Martes",    "capsula",     "💡"),
    (2, "Miércoles", "trivia",      "🧠"),
    (3, "Jueves",    "historia",    "📖"),
    (4, "Viernes",   "classic",     "🎙️"),
    (5, "Sábado",    "classic",     "🎙️"),
    (6, "Domingo",   "classic",     "🎙️"),
]


@router.post("/generate-parrilla", response_model=ParrillaOut)
async def generate_parrilla(
    body: ParrillaRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Genera la parrilla semanal de radio: 7 cuñas con 1 clic.

    - Starter: 7 variaciones del modo classic
    - Growth:  4 modos distintos + classic los últimos días
    - Pro+:    Los 7 modos completos con máxima variedad

    Si auto_schedule=True (solo Growth+), programa el envío por Celery.
    """
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    if current_user.subscription_status not in ("active", "trial"):
        raise HTTPException(status_code=402, detail="Necesitas un plan activo")

    plan = current_user.current_plan or "starter"

    # Seleccionar tabla de modos según plan
    if plan in ("pro", "business", "enterprise"):
        schedule_table = _PARRILLA_ALL
    elif plan == "growth":
        schedule_table = _PARRILLA_GROWTH
    else:  # starter / trial
        schedule_table = _PARRILLA_STARTER

    # Auto-schedule solo disponible para Growth+
    can_auto = plan in ("growth", "pro", "business", "enterprise")
    auto_scheduled = body.auto_schedule and can_auto

    days_out: list[ParrillaDayOut] = []

    for day_num, day_name, mode, emoji in schedule_table:
        try:
            day_context = f"Haz este mensaje específico para el día {day_name}, dale un ángulo único."
            combined_context = f"{body.extra_context} - {day_context}" if body.extra_context else day_context

            script = await generate_radio_script(
                business_name=body.business_name,
                message_or_intent=body.intent,
                country=body.country,
                mode=mode,
                business_category=body.business_category,
                extra_context=combined_context,
            )
            try:
                audio_url = await generate_radio_ad(
                    business_name=body.business_name,
                    message_or_intent=body.intent,
                    country=body.country,
                    _script=script,
                    mode=mode,
                    business_category=body.business_category,
                )
            except Exception as audio_err:
                logger.warning("[PARRILLA] Audio day %d failed: %s", day_num, audio_err)
                audio_url = None

            days_out.append(ParrillaDayOut(
                day=day_num,
                day_name=day_name,
                mode=mode,
                mode_emoji=emoji,
                script=script,
                audio_url=audio_url,
            ))

            # Small delay to avoid rate limits on Claude/TTS
            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error("[PARRILLA] Script day %d failed: %s", day_num, e)
            days_out.append(ParrillaDayOut(
                day=day_num,
                day_name=day_name,
                mode=mode,
                mode_emoji=emoji,
                script=f"[Error generando guión: {e}]",
                audio_url=None,
            ))

    # Auto-schedule: programar envío a contactos activos cada día de la semana
    if auto_scheduled:
        from datetime import datetime, timezone, timedelta
        from app.workers.tasks import send_parrilla_day

        try:
            hour, minute = (int(x) for x in body.send_time.split(":"))
        except Exception:
            hour, minute = 10, 0

        now = datetime.now(timezone.utc)
        for day_out in days_out:
            if day_out.audio_url:  # solo programar días con audio OK
                # días hasta el próximo día de semana correspondiente
                days_ahead = (day_out.day - now.weekday()) % 7
                send_dt = (now + timedelta(days=days_ahead)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                countdown = max(60, int((send_dt - now).total_seconds()))
                send_parrilla_day.apply_async(
                    kwargs={
                        "advertiser_id": str(current_user.id),
                        "audio_url": day_out.audio_url,
                        "script": day_out.script,
                        "day_name": day_out.day_name,
                        "mode": day_out.mode,
                    },
                    countdown=countdown,
                    queue="whatsapp",
                )

    return ParrillaOut(
        days=days_out,
        plan=plan,
        auto_scheduled=auto_scheduled,
    )
