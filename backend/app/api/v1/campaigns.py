"""
Campaigns router — /api/v1/campaigns
"""
import csv
import io
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from redis.asyncio import Redis as AsyncRedis
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from slowapi.util import get_remote_address
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.api.idempotency import idempotent_post, store_idempotency_response
from app.api.rate_limit import limiter
from app.core.redis import get_redis_optional
from app.database import get_db
from app.models.campaign import Campaign
from app.models.customer_story import CustomerStory
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
    CustomerStoryOut,
    CustomerStoryListOut,
)
from app.services.claude_service import (
    generate_campaign_variants,
    generate_sequence_messages,
    generate_saga_episodes,
    generate_voces_capsule,
)
from app.services.imagen_service import generate_flyer
from app.services.radio_service import generate_radio_ad, generate_radio_script
from app.workers.tasks import schedule_campaign

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("")
async def list_campaigns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(Campaign)
        .where(Campaign.advertiser_id == current_user.id)
        .order_by(Campaign.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    total_result = await db.execute(
        select(func.count()).select_from(Campaign)
        .where(Campaign.advertiser_id == current_user.id)
    )
    total = total_result.scalar_one()
    items = [CampaignOut.model_validate(c) for c in result.scalars().all()]
    return {"items": [i.model_dump() for i in items], "total": total}


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_campaign(
    request: Request,
    body: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(idempotent_post),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> CampaignOut:
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

    out = CampaignOut.model_validate(campaign)
    await store_idempotency_response(request, redis, out.model_dump())
    return out


@router.patch("/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CampaignOut:
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
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(idempotent_post),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict[str, str]:
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
    out = {"message": "Campaña pausada"}
    await store_idempotency_response(request, redis, out)
    return out


@router.post("/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(idempotent_post),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict[str, str]:
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
    out = {"message": "Campaña reanudada"}
    await store_idempotency_response(request, redis, out)
    return out


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
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
) -> dict:
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


@router.get("/export-csv")
async def export_campaigns_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Export all campaigns with stats as a CSV file."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.advertiser_id == current_user.id)
        .order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Nombre", "Tipo", "Estado", "Enviados", "Entregados",
        "Leídos", "Respondidos", "Fallidos", "Cupones Canjeados",
        "% Entrega", "% Respuesta", "Creada"
    ])
    for c in campaigns:
        s = c.stats
        sent = s.get("sent", 0) or 0
        delivered = s.get("delivered", 0) or 0
        replied = s.get("replied", 0) or 0
        pct_delivery = round((delivered / sent * 100), 1) if sent > 0 else 0
        pct_reply = round((replied / sent * 100), 1) if sent > 0 else 0
        writer.writerow([
            c.name, c.type, c.status,
            sent, delivered,
            s.get("read", 0) or 0, replied,
            s.get("failed", 0) or 0, s.get("coupons_redeemed", 0) or 0,
            f"{pct_delivery}%", f"{pct_reply}%",
            c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=campanas_iaradio.csv"},
    )


class PublicCustomerStoryOut(BaseModel):
    id: uuid.UUID
    business_name: str | None = None
    transcription: str
    media_url: str
    sentiment: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/stories/public")
async def list_public_stories(
    db: AsyncSession = Depends(get_db),
) -> list[PublicCustomerStoryOut]:
    """Return approved Customer Stories publicly (no auth required)."""
    from sqlalchemy.orm import joinedload

    result = await db.execute(
        select(CustomerStory)
        .options(joinedload(CustomerStory.advertiser))
        .where(CustomerStory.approved == True)
        .order_by(CustomerStory.created_at.desc())
        .limit(20)
    )
    stories = result.unique().scalars().all()

    return [
        PublicCustomerStoryOut(
            id=s.id,
            business_name=s.advertiser.business_name if s.advertiser else None,
            transcription=s.transcription,
            media_url=s.media_url,
            sentiment=s.sentiment,
            created_at=s.created_at,
        )
        for s in stories
    ]


class ABTestSetup(BaseModel):
    variant_b: str  # alternative message text


@router.post("/{campaign_id}/ab-test")
async def setup_ab_test(
    campaign_id: uuid.UUID,
    body: ABTestSetup,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CampaignOut:
    """Enable A/B testing on a campaign with an alternate message variant."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.advertiser_id == current_user.id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    campaign.ab_test = {
        "enabled": True,
        "variant_b": body.variant_b,
        "stats_a": {"sent": 0, "replied": 0},
        "stats_b": {"sent": 0, "replied": 0},
    }
    await db.commit()
    await db.refresh(campaign)
    return CampaignOut.model_validate(campaign)


class BannerPreviewRequest(BaseModel):
    promo_description: str
    business_name: str
    contact_name: str = "Juan"
    palette: str = ""
    layout: str = ""
    business_category: str = ""


@router.post("/banner/preview")
async def preview_banner(
    body: BannerPreviewRequest,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Generate and return a preview PNG banner (no R2 upload, no DB write)."""
    from fastapi.responses import Response as FastAPIResponse
    from app.services.banner_service import (
        generate_banner_png, generate_banner_copy_with_claude, select_design,
    )

    design = select_design(body.business_category or current_user.business_category, None)
    palette = body.palette or design.palette
    layout = body.layout or design.layout

    copy = await generate_banner_copy_with_claude(
        business_name=body.business_name,
        contact_name=body.contact_name,
        promo_description=body.promo_description,
        business_category=body.business_category or current_user.business_category,
    )
    png_bytes = generate_banner_png(copy, palette, layout)
    return FastAPIResponse(content=png_bytes, media_type="image/png")


@router.post("/generate-content", response_model=GenerateContentResponse)
async def generate_content(
    body: GenerateContentRequest,
    current_user: User = Depends(get_current_user),
) -> GenerateContentResponse:
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
) -> dict[str, str]:
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
) -> GenerateSequenceResponse:
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
) -> GenerateSequenceResponse:
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
) -> dict[str, str]:
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
        voice_id=body.voice_id,
    )
    return {"audio_url": audio_url, "script": script}


@router.post("/{campaign_id}/generate-capsule")
async def generate_capsule(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Generate a Voces del Barrio narrative capsule from approved customer stories."""
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.advertiser_id == current_user.id,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    if campaign.type != "voces":
        raise HTTPException(status_code=400, detail="Esta campaña no es de tipo voces")

    stories_result = await db.execute(
        select(CustomerStory)
        .options(selectinload(CustomerStory.contact))
        .where(
            CustomerStory.campaign_id == campaign_id,
            CustomerStory.approved == True,
        )
    )
    stories = stories_result.scalars().all()
    if not stories:
        raise HTTPException(
            status_code=400,
            detail="No hay historias aprobadas para generar la cápsula. "
                   "Espera a que los clientes envíen audios y los apruebes.",
        )

    stories_data = [
        {"name": s.contact.name if s.contact else "Cliente", "text": s.transcription}
        for s in stories
    ]

    business_name = current_user.business_name or "Mi negocio"
    script = await generate_voces_capsule(
        business_name=business_name,
        stories=stories_data,
        campaign_intent=campaign.message_text,
    )

    audio_url = await generate_radio_ad(
        business_name=business_name,
        message_or_intent=script,
        country="mx",
        _script=script,
        mode="comunitaria",
        business_category=None,
    )

    return {"audio_url": audio_url, "script": script}


@router.get("/{campaign_id}/stories", response_model=CustomerStoryListOut)
async def list_campaign_stories(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CustomerStoryListOut:
    """List all customer stories for a Voces campaign."""
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.advertiser_id == current_user.id,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    stories_result = await db.execute(
        select(CustomerStory)
        .options(selectinload(CustomerStory.contact))
        .where(
            CustomerStory.campaign_id == campaign_id,
        ).order_by(CustomerStory.created_at.desc())
    )
    stories = stories_result.scalars().all()

    out = []
    for s in stories:
        contact_name = s.contact.name if s.contact else None
        out.append(CustomerStoryOut(
            id=s.id,
            contact_id=s.contact_id,
            contact_name=contact_name,
            media_url=s.media_url,
            transcription=s.transcription,
            sentiment=s.sentiment,
            approved=s.approved,
            created_at=s.created_at,
        ))

    return CustomerStoryListOut(
        stories=out,
        total=len(out),
        approved_count=sum(1 for s in stories if s.approved),
        pending_count=sum(1 for s in stories if not s.approved),
    )


@router.patch("/stories/{story_id}/approve")
async def approve_story(
    story_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Toggle approval of a customer story."""
    result = await db.execute(
        select(CustomerStory).where(
            CustomerStory.id == story_id,
            CustomerStory.advertiser_id == current_user.id,
        )
    )
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Historia no encontrada")

    story.approved = not story.approved
    await db.commit()
    return {"approved": story.approved}


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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ParrillaOut:
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
                    day_variant=day_num,
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

    # Guardar siempre en base de datos. Programar solo si auto_scheduled.
    from datetime import datetime, timezone, timedelta

    try:
        hour, minute = (int(x) for x in body.send_time.split(":"))
    except Exception:
        logger.warning("[CAMPAIGN] Failed to parse send_time, defaulting to 10:00", exc_info=True)
        hour, minute = 10, 0

    now = datetime.now(timezone.utc)
    for day_out in days_out:
        if day_out.audio_url:  # solo guardar días con audio OK
            # días hasta el próximo día de semana correspondiente
            days_ahead = (day_out.day - now.weekday()) % 7
            
            # Si es para hoy pero ya pasó la hora, programar para la siguiente semana
            send_dt_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if days_ahead == 0 and now > send_dt_today:
                days_ahead += 7

            send_dt = (now + timedelta(days=days_ahead)).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            
            campaign = Campaign(
                advertiser_id=current_user.id,
                name=f"Parrilla: {day_out.day_name}",
                type="promo",
                message_text=day_out.script,
                status="scheduled" if auto_scheduled else "draft",
                ab_test={
                    "campaign_mode": "radio",
                    "audio_url": day_out.audio_url,
                    "radio_script": day_out.script,
                },
                schedule={"start_date": send_dt.isoformat().replace("+00:00", "Z")}
            )
            db.add(campaign)
            await db.commit()
            await db.refresh(campaign)

            if auto_scheduled:
                countdown = max(60, int((send_dt - now).total_seconds()))
                schedule_campaign.apply_async(
                    args=[str(campaign.id)],
                    countdown=countdown,
                )

    return ParrillaOut(
        days=days_out,
        plan=plan,
        auto_scheduled=auto_scheduled,
    )
