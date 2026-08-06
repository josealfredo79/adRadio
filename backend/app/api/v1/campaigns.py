"""
Campaigns router — /api/v1/campaigns
"""
import csv
import io
import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from redis.asyncio import Redis as AsyncRedis
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, check_feature_access, get_radio_limit
from app.api.idempotency import idempotent_post, store_idempotency_response
from app.core.rate_limiter import limiter
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
    ParrillaJobOut,
    ParrillaStatusOut,
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
from app.services.analytics_service import capture_event
from app.services.banner_service import generate_banner_png, generate_banner_copy_with_claude, select_design
from app.services.radio_service import generate_radio_ad, generate_radio_script
from app.workers.tasks import schedule_campaign, generate_parrilla_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("")
async def list_campaigns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.models.message import Message

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
    campaigns = result.scalars().all()

    # Message counts per campaign
    campaign_ids = [c.id for c in campaigns]
    counts_raw = await db.execute(
        select(Message.campaign_id, Message.status, func.count(Message.id))
        .where(Message.campaign_id.in_(campaign_ids))
        .group_by(Message.campaign_id, Message.status)
    )
    counts: dict[uuid.UUID, dict[str, int]] = {}
    for row in counts_raw:
        cid, status, cnt = row
        counts.setdefault(cid, {})[status] = cnt

    items = []
    for c in campaigns:
        out = CampaignOut.model_validate(c)
        out.message_counts = counts.get(c.id, {})
        items.append(out.model_dump())

    return {"items": items, "total": total}


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

    if not body.name or not body.name.strip():
        raise HTTPException(status_code=422, detail="El nombre de la campaña es obligatorio")

    if not body.message_text or not body.message_text.strip():
        raise HTTPException(status_code=422, detail="El mensaje de la campaña es obligatorio")

    valid_types = {"promo", "reminder", "launch", "event", "voces"}
    if body.type not in valid_types:
        raise HTTPException(status_code=422, detail=f"Tipo de campaña inválido. Debe ser uno de: {', '.join(sorted(valid_types))}")

    if body.status not in ("draft", "scheduled"):
        raise HTTPException(status_code=422, detail="El estado debe ser 'draft' o 'scheduled'")

    try:
        campaign = Campaign(advertiser_id=current_user.id, **body.model_dump())
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
    except Exception as e:
        await db.rollback()
        logger.error("Error al crear campaña: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al guardar la campaña. Intenta de nuevo.")

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

    capture_event("campaign_created", user_id=current_user.id, properties={
        "campaign_id": str(campaign.id),
        "type": campaign.type,
        "mode": (campaign.ab_test or {}).get("campaign_mode", "regular"),
    })
    out = CampaignOut.model_validate(campaign)
    await store_idempotency_response(request, redis, out.model_dump(mode="json"))
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
    mode = (campaign.ab_test or {}).get("campaign_mode", "regular")
    if campaign.status == "draft":
        if mode in ("radio", "comunitaria") and not (campaign.ab_test or {}).get("audio_url"):
            raise HTTPException(status_code=400, detail="Completa la generación de audio antes de enviar la campaña")
        if mode in ("banner",) and not campaign.image_url:
            raise HTTPException(status_code=400, detail="Completa la generación del banner antes de enviar la campaña")
        if not campaign.message_text and mode == "regular":
            raise HTTPException(status_code=400, detail="Agrega un mensaje a la campaña antes de enviarla")
    if campaign.status not in ("draft", "scheduled", "paused"):
        raise HTTPException(status_code=400, detail="La campaña no puede ser reanudada desde su estado actual")
    campaign.status = "running"
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error("Error al reanudar campaña %s: %s", campaign_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error al iniciar la campaña. Intenta de nuevo.")
    schedule_campaign.delay(str(campaign.id))
    capture_event("campaign_sent", user_id=current_user.id, properties={
        "campaign_id": str(campaign.id),
        "type": campaign.type,
        "mode": mode,
    })
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
    if not check_feature_access(current_user, "ab_testing"):
        raise HTTPException(status_code=402, detail="Tu plan no incluye A/B testing. Actualiza a Business o superior.")
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
    capture_event("content_generated", user_id=current_user.id, properties={
        "campaign_type": body.campaign_type,
        "variants_count": len(variants),
    })
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
        business_category=body.business_category,
    )
    return {"image_url": image_url}


@router.post("/generate-sequence", response_model=GenerateSequenceResponse)
async def generate_sequence(
    body: GenerateSequenceRequest,
    current_user: User = Depends(get_current_user),
) -> GenerateSequenceResponse:
    """Genera una secuencia de 3 mensajes para campaña en días distintos."""
    if not check_feature_access(current_user, "sequence"):
        raise HTTPException(status_code=402, detail="Tu plan no incluye campañas secuencia. Actualiza a Pro o superior.")
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
    if not check_feature_access(current_user, "saga"):
        raise HTTPException(status_code=402, detail="Tu plan no incluye campañas saga. Actualiza a Business o superior.")
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
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Genera una cuña publicitaria completa en audio:
    Claude escribe el guión → edge-tts pone voz de locutor → sube a R2.
    Retorna URL del audio .ogg listo para enviar como nota de voz por WhatsApp.
    """
    limit = get_radio_limit(current_user)
    if limit == 0:
        raise HTTPException(status_code=402, detail="Tu plan no incluye cuñas de radio. Actualiza a Growth o superior.")
    if limit > 0:
        from app.models.campaign import Campaign
        from datetime import datetime, timezone, timedelta
        period_start = datetime.now(timezone.utc) - timedelta(days=30)
        count_result = await db.execute(
            select(func.count()).select_from(Campaign).where(
                Campaign.advertiser_id == current_user.id,
                Campaign.created_at >= period_start,
                Campaign.type.in_(["radio", "comunitaria", "capsula", "trivia", "historia", "alerta", "estacional"]),
            )
        )
        used = count_result.scalar() or 0
        if used >= limit:
            if limit == 1:
                msg = "Ya usaste tu única cuña de radio disponible en tu plan. Actualiza a Growth para más."
            else:
                msg = f"Has alcanzado el límite de {limit} cuñas de radio de tu plan. Actualiza a Pro para cuñas ilimitadas."
            raise HTTPException(status_code=402, detail=msg)
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
        include_sfx=body.include_sfx,
    )
    capture_event("radio_ad_generated", user_id=current_user.id, properties={
        "mode": body.mode,
        "country": body.country,
    })
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


@router.post("/generate-parrilla", response_model=ParrillaJobOut, status_code=status.HTTP_202_ACCEPTED)
async def generate_parrilla(
    body: ParrillaRequest,
    current_user: User = Depends(get_current_user),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> ParrillaJobOut:
    """
    Encola la generación de la parrilla semanal (7 cuñas/banners) en un worker
    de Celery y devuelve un job_id de inmediato.

    La generación real (guiones con Claude + audio/banners, 7 días) tarda
    minutos — sostenerla dentro del propio request HTTP la deja a merced de
    timeouts del navegador/proxy, y si el cliente se desconecta a medias el
    resultado se pierde sin que nadie se entere si terminó o no. El progreso
    se consulta con GET /generate-parrilla/{job_id}.
    """
    if current_user.subscription_status not in ("active", "trial"):
        raise HTTPException(status_code=402, detail="Necesitas un plan activo")

    if redis is None:
        raise HTTPException(status_code=503, detail="Servicio de generación no disponible temporalmente")

    plan = current_user.current_plan or "starter"
    can_auto = plan in ("growth", "pro", "business", "enterprise")

    job_id = str(uuid.uuid4())
    initial_state = {
        "advertiser_id": str(current_user.id),
        "status": "pending",
        "total_days": 7,
        "current_day": 0,
        "days": [],
        "plan": plan,
        "auto_scheduled": body.auto_schedule and can_auto,
        "error": None,
    }
    await redis.set(f"parrilla_job:{job_id}", json.dumps(initial_state), ex=3600)

    generate_parrilla_task.delay(job_id, str(current_user.id), body.model_dump())

    return ParrillaJobOut(job_id=job_id)


@router.get("/generate-parrilla/{job_id}", response_model=ParrillaStatusOut)
async def get_parrilla_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> ParrillaStatusOut:
    if redis is None:
        raise HTTPException(status_code=503, detail="Servicio no disponible temporalmente")

    raw = await redis.get(f"parrilla_job:{job_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Job no encontrado o expirado")

    data = json.loads(raw)
    if data.pop("advertiser_id", None) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Job no encontrado o expirado")

    return ParrillaStatusOut(**data)
