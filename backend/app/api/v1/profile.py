"""
Profile & Dashboard router — /api/v1/me, /api/v1/dashboard
"""
import json
import logging
import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from redis.asyncio import Redis as AsyncRedis
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, check_feature_access
from app.api.idempotency import idempotent_post, store_idempotency_response
from app.core.redis import get_redis_optional
from app.database import get_db
from app.models.automation import AutomationFlow
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.customer_story import CustomerStory
from app.models.order import Order
from app.models.user import User
from app.services.storage_service import upload_bytes
from app.schemas.auth import UserOut
from app.schemas.profile import ProfileUpdate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["profile"])


class WhiteLabelOut(BaseModel):
    primary_color: str = "#6366f1"
    app_name: str = ""
    hide_branding: bool = False
    custom_domain: str = ""
    favicon_url: str = ""


class WhiteLabelUpdate(BaseModel):
    primary_color: str | None = None
    app_name: str | None = None
    hide_branding: bool | None = None
    custom_domain: str | None = None
    favicon_url: str | None = None


@router.get("/me", response_model=UserOut)
async def get_profile(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.get("/me/referral")
async def get_referral_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Código propio de referido + cuántas personas se registraron con él y
    cuántas de esas ya son clientes de pago (activaron una recompensa)."""
    referred_result = await db.execute(
        select(func.count()).select_from(User).where(User.referred_by_id == current_user.id)
    )
    paying_result = await db.execute(
        select(func.count()).select_from(User).where(
            User.referred_by_id == current_user.id, User.referral_rewarded.is_(True),
        )
    )
    return {
        "code": current_user.referral_code,
        "referred_count": referred_result.scalar() or 0,
        "paying_referrals": paying_result.scalar() or 0,
    }


@router.patch("/me", response_model=UserOut)
async def update_profile(
    body: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(current_user, field, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Ese link ya está en uso, elige otro")
    await db.refresh(current_user)
    return UserOut.model_validate(current_user)


ALLOWED_LOGO_MIME_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_LOGO_SIZE = 5 * 1024 * 1024  # 5MB


@router.post("/me/logo", response_model=UserOut)
async def upload_logo(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserOut:
    """Sube el logo del negocio, usado en la landing page pública (/sitio/{slug})."""
    if file.content_type not in ALLOWED_LOGO_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Tipo de archivo no soportado: {file.content_type}")

    content = await file.read()
    if len(content) > MAX_LOGO_SIZE:
        raise HTTPException(status_code=413, detail="La imagen supera el límite de 5MB")

    ext = ALLOWED_LOGO_MIME_TYPES[file.content_type]
    key = f"logos/{current_user.id}/{uuid.uuid4()}.{ext}"
    url = await upload_bytes(content, key, file.content_type)
    if not url:
        raise HTTPException(status_code=502, detail="No se pudo guardar el logo")

    current_user.logo_url = url
    await db.commit()
    await db.refresh(current_user)
    return UserOut.model_validate(current_user)


MAX_HERO_IMAGE_SIZE = 8 * 1024 * 1024  # 8MB — foto de portada, más grande que el logo


@router.post("/me/hero-image", response_model=UserOut)
async def upload_hero_image(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserOut:
    """Sube la foto de portada del header de la landing pública (/sitio/{slug})."""
    if file.content_type not in ALLOWED_LOGO_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Tipo de archivo no soportado: {file.content_type}")

    content = await file.read()
    if len(content) > MAX_HERO_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="La imagen supera el límite de 8MB")

    ext = ALLOWED_LOGO_MIME_TYPES[file.content_type]
    key = f"hero-images/{current_user.id}/{uuid.uuid4()}.{ext}"
    url = await upload_bytes(content, key, file.content_type)
    if not url:
        raise HTTPException(status_code=502, detail="No se pudo guardar la foto de portada")

    current_user.hero_image_url = url
    await db.commit()
    await db.refresh(current_user)
    return UserOut.model_validate(current_user)


class TaglineSuggestRequest(BaseModel):
    hint: str = ""


class TaglineSuggestResponse(BaseModel):
    suggestions: list[str]


@router.post("/me/landing-tagline/suggest", response_model=TaglineSuggestResponse)
async def suggest_landing_tagline(
    body: TaglineSuggestRequest,
    current_user: User = Depends(get_current_user),
):
    """Sugiere taglines para la landing page usando el perfil del negocio
    (y opcionalmente una idea libre del cliente) — el cliente elige o edita,
    nunca se publica nada sin que él confirme."""
    from app.services.llm_client import chat_completion

    context_lines = [
        f"Negocio: {current_user.business_name or 'Negocio'}",
        f"Categoría: {current_user.business_category or 'General'}",
    ]
    if current_user.bot_instructions:
        context_lines.append(f"Contexto adicional: {current_user.bot_instructions[:300]}")
    if body.hint.strip():
        context_lines.append(f"Idea del dueño: {body.hint.strip()[:300]}")

    prompt = (
        "Eres un experto en marketing para pequeños negocios en Latinoamérica.\n"
        "Genera 3 frases cortas (taglines) para la página web de este negocio.\n\n"
        + "\n".join(context_lines)
        + "\n\nReglas: máximo 140 caracteres cada una, en español, sin comillas, "
        "atractivas para un cliente que visita la página por primera vez.\n\n"
        'Responde ÚNICAMENTE con un JSON: {"suggestions": ["frase 1", "frase 2", "frase 3"]}'
    )

    # 600, no 350: algunos modelos gratis de OpenRouter razonan antes de
    # responder (tokens ocultos que sí cuentan contra max_tokens) y a veces
    # agotan el budget completo sin llegar a escribir el JSON visible,
    # devolviendo contenido vacío — verificado empíricamente ~1 de cada 3
    # intentos con 350. Un reintento adicional es la segunda capa (mismo
    # patrón sugerido para el bug análogo de TTS).
    #
    # Verificado en vivo 2026-08-09: el modelo gratis también puede pegarle
    # a un 429 de rate-limit del pool compartido de OpenRouter, no solo
    # devolver vacío — los 2 intentos gratis fallaron seguidos en una prueba
    # real. Como este endpoint es de bajo volumen (un dueño de negocio
    # generando tagline, no tráfico de bot), un 3er intento con Claude
    # Haiku directo (force_anthropic=True) es un fallback confiable barato
    # en vez de dejar al usuario con un 502.
    suggestions: list[str] = []
    last_error: Exception | None = None
    for _attempt in range(3):
        try:
            raw = await chat_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=600, temperature=0.8,
                anthropic_model="claude-haiku-4-5-20251001",
                force_anthropic=(_attempt == 2),
            )
            # Claude (rama Anthropic) a veces envuelve el JSON en un code
            # fence de markdown (```json ... ```) aunque se le pida "solo
            # JSON" — verificado en vivo probando el fallback de este mismo
            # endpoint. El modelo gratis de OpenRouter no lo hizo en las
            # pruebas, pero quitar el fence es inofensivo si no hay ninguno.
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned)
            data = json.loads(cleaned)
            suggestions = [s.strip()[:140] for s in data.get("suggestions", []) if s.strip()][:3]
            if not suggestions:
                raise ValueError("empty suggestions")
            break
        except Exception as e:
            last_error = e
            continue

    if not suggestions:
        logger.warning("[LANDING] Tagline suggestion failed after retry+Anthropic fallback: %s", last_error)
        raise HTTPException(status_code=502, detail="No se pudieron generar sugerencias, intenta de nuevo")

    return TaglineSuggestResponse(suggestions=suggestions)


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


@router.post("/me/change-password")
async def change_password(
    request: Request,
    body: ChangePasswordBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(idempotent_post),
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict[str, str]:
    """Change the current user's password after verifying the old one."""
    from app.core.security import verify_password, hash_password

    current_pw = body.current_password.strip()
    new_pw = body.new_password.strip()

    if not current_pw or not new_pw:
        raise HTTPException(status_code=400, detail="Debes proporcionar la contraseña actual y la nueva")
    if len(new_pw) < 8:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 8 caracteres")
    if not verify_password(current_pw, current_user.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")

    current_user.password_hash = hash_password(new_pw)
    await db.commit()
    logger.info("Password changed for user %s", current_user.id)
    out: dict[str, str] = {"message": "Contraseña actualizada correctamente"}
    await store_idempotency_response(request, redis, out)
    return out


@router.get("/dashboard")
async def dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis_optional),
):
    if redis:
        cache_key = f"dashboard:{current_user.id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

    # Contacts count
    contacts_total = await db.execute(
        select(func.count()).where(
            Contact.advertiser_id == current_user.id,
            Contact.status == "active",
        )
    )

    # Campaigns active
    campaigns_active = await db.execute(
        select(func.count()).where(
            Campaign.advertiser_id == current_user.id,
            Campaign.status.in_(["running", "scheduled"]),
        )
    )

    # Messages sent this month
    # Active automations
    automations_active = await db.execute(
        select(func.count()).where(
            AutomationFlow.advertiser_id == current_user.id,
            AutomationFlow.is_active == True,
        )
    )

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    messages_sent = await db.execute(
        select(func.count()).where(
            Message.advertiser_id == current_user.id,
            Message.direction == "outbound",
            Message.created_at >= first_of_month,
        )
    )

    # Orders confirmed (all time)
    orders_confirmed = await db.execute(
        select(func.count()).where(
            Order.advertiser_id == current_user.id,
            Order.state == "confirmed",
        )
    )
    # Orders pending (in-progress)
    orders_pending = await db.execute(
        select(func.count()).where(
            Order.advertiser_id == current_user.id,
            Order.state.notin_(["confirmed", "cancelled"]),
        )
    )
    # Voces del Barrio — historias esperando aprobación
    voces_stories_pending = await db.execute(
        select(func.count()).where(
            CustomerStory.advertiser_id == current_user.id,
            CustomerStory.status == "pending",
        )
    )

    # Leads del bot — contactos creados vía WhatsApp este mes
    leads_from_bot = await db.execute(
        select(func.count()).where(
            Contact.advertiser_id == current_user.id,
            Contact.source == "landing",
            Contact.created_at >= first_of_month,
        )
    )
    # Solicitudes de plan (órdenes en plan_pending_confirmation)
    plan_requests = await db.execute(
        select(func.count()).where(
            Order.advertiser_id == current_user.id,
            Order.state == "plan_pending_confirmation",
        )
    )
    # Leads sin respuesta — contactos cuya última interacción fue inbound sin reply
    last_in = (
        select(
            Message.contact_id,
            Message.direction,
            func.row_number().over(
                partition_by=Message.contact_id,
                order_by=Message.created_at.desc(),
            ).label("rn"),
        )
        .where(
            Message.advertiser_id == current_user.id,
            Message.created_at >= first_of_month,
        )
        .subquery()
    )
    unreplied = await db.execute(
        select(func.count()).select_from(
            select(last_in.c.contact_id)
            .where(last_in.c.rn == 1, last_in.c.direction == "inbound")
            .subquery()
        )
    )

    # Engagement distribution — hot/warm/cold among active contacts.
    # Thresholds match workers/tasks.py::update_contact_engagement_score.
    engagement_rows = await db.execute(
        select(
            func.count().filter(Contact.engagement_score >= 80).label("hot"),
            func.count().filter(
                Contact.engagement_score >= 40, Contact.engagement_score < 80
            ).label("warm"),
            func.count().filter(Contact.engagement_score < 40).label("cold"),
        ).where(
            Contact.advertiser_id == current_user.id,
            Contact.status == "active",
        )
    )
    engagement_row = engagement_rows.one()

    # Coupon redemption — closed-loop attribution from campaign to WhatsApp reply.
    coupon_rows = await db.execute(
        select(
            func.count().label("issued"),
            func.count().filter(Coupon.used_count > 0).label("redeemed"),
        ).where(Coupon.advertiser_id == current_user.id)
    )
    coupon_row = coupon_rows.one()
    coupons_issued = coupon_row.issued or 0
    coupons_redeemed = coupon_row.redeemed or 0
    redemption_rate = (
        round(coupons_redeemed / coupons_issued * 100, 1) if coupons_issued > 0 else 0.0
    )

    data = {
        "contacts_total": contacts_total.scalar_one(),
        "campaigns_active": campaigns_active.scalar_one(),
        "automations_active": automations_active.scalar_one(),
        "messages_sent_this_month": messages_sent.scalar_one(),
        "messages_remaining": current_user.messages_remaining,
        "plan": current_user.current_plan,
        "subscription_status": current_user.subscription_status,
        "orders_confirmed": orders_confirmed.scalar_one(),
        "orders_pending": orders_pending.scalar_one(),
        "voces_stories_pending": voces_stories_pending.scalar_one(),
        "leads_from_bot": leads_from_bot.scalar_one(),
        "plan_requests": plan_requests.scalar_one(),
        "leads_unreplied": unreplied.scalar_one(),
        "engagement": {
            "hot": engagement_row.hot or 0,
            "warm": engagement_row.warm or 0,
            "cold": engagement_row.cold or 0,
        },
        "coupons": {
            "issued": coupons_issued,
            "redeemed": coupons_redeemed,
            "redemption_rate": redemption_rate,
        },
    }

    if redis:
        await redis.setex(cache_key, 120, json.dumps(data))  # cache 2 min
    return data


@router.get("/dashboard/chart")
async def dashboard_chart(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis_optional),
):
    """Returns outbound message counts for the last 7 days."""
    from datetime import datetime, timezone, timedelta

    if redis:
        cache_key = f"dashboard_chart:{current_user.id}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

    now = datetime.now(timezone.utc)
    seven_days_ago = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)

    rows = await db.execute(
        select(
            func.date(Message.created_at).label("day"),
            func.count().label("mensajes"),
        ).where(
            Message.advertiser_id == current_user.id,
            Message.direction == "outbound",
            Message.created_at >= seven_days_ago,
        ).group_by(
            func.date(Message.created_at),
        ).order_by(
            func.date(Message.created_at),
        )
    )

    counts_map: dict[str, int] = {}
    for row in rows:
        counts_map[row.day.isoformat()] = row.mensajes

    days = []
    for i in range(7):
        day = (seven_days_ago + timedelta(days=i))
        day_str = day.date().isoformat()
        days.append({
            "day": day.strftime("%a"),
            "mensajes": counts_map.get(day_str, 0),
            "date": day_str,
        })

    if redis:
        await redis.setex(cache_key, 120, json.dumps(days))
    return days


@router.get("/profile/white-label", response_model=WhiteLabelOut)
async def get_white_label(
    current_user: User = Depends(get_current_user),
):
    if not check_feature_access(current_user, "white_label"):
        raise HTTPException(status_code=402, detail="Tu plan no incluye white-label. Actualiza a Enterprise.")
    wl = current_user.white_label or {}
    return WhiteLabelOut(**wl)


@router.patch("/profile/white-label", response_model=WhiteLabelOut)
async def update_white_label(
    body: WhiteLabelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not check_feature_access(current_user, "white_label"):
        raise HTTPException(status_code=402, detail="Tu plan no incluye white-label. Actualiza a Enterprise.")
    wl = dict(current_user.white_label or {})
    for field, value in body.model_dump(exclude_none=True).items():
        wl[field] = value
    current_user.white_label = wl
    await db.commit()
    await db.refresh(current_user)
    return WhiteLabelOut(**current_user.white_label)
