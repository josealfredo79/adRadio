"""Entrar al panel con WhatsApp — /api/v1/auth/whatsapp

Para los dueños que se dieron de alta en el chat de IaRadio (sin correo ni
contraseña, ver services/owner_signup.py), y para cualquier dueño cuyo
WhatsApp personal (Configuración → "Tu WhatsApp") sea ese número.

- POST /code    manda un código por WhatsApp (mismos topes que /mi y el QR).
- POST /verify  código correcto → sesión del panel, si el número es de un dueño.
- POST /signup  código correcto → crea el negocio con lo que contó en el chat
                y abre su sesión. Si el número ya era de un dueño, solo entra.

Vive bajo /auth para que la cookie del refresh (path /api/v1/auth) quede igual
que con el login normal.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import issue_session
from app.config import settings
from app.core.bot_guard import is_honeypot_hit
from app.core.rate_limiter import limiter
from app.core.redis import get_redis_optional
from app.database import get_db
from app.services.analytics_service import capture_event
from app.services.customer_account import (
    CodeError,
    canonical_phone,
    check_code,
    issue_code,
    send_code,
)
from app.services.owner_signup import create_owner, owner_by_phone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/whatsapp", tags=["auth"])


def _phone(raw) -> str:
    phone = canonical_phone(str(raw or ""))
    if phone is None:
        raise HTTPException(status_code=400, detail="Escribe tu número de WhatsApp a 10 dígitos")
    return phone


def _need_redis(redis: AsyncRedis | None) -> AsyncRedis:
    if not settings.CUSTOMER_ACCOUNT_ENABLED or redis is None:
        raise HTTPException(status_code=503, detail="Por ahora no podemos mandar códigos. Intenta en un rato.")
    return redis


async def _checked(redis: AsyncRedis, phone: str, code) -> None:
    if not await check_code(redis, phone, str(code or "")):
        raise HTTPException(status_code=400, detail="Código incorrecto o vencido")


@router.post("/code")
@limiter.limit("5/minute")
async def request_code(
    request: Request, body: dict, redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict:
    redis = _need_redis(redis)
    phone = _phone(body.get("phone"))
    if is_honeypot_hit(body, request, "owner_code"):
        return {"message": "Te mandamos un código por WhatsApp."}
    try:
        code = await issue_code(redis, phone)
    except CodeError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    if not await send_code(phone, code):
        raise HTTPException(status_code=503, detail="No pudimos mandarte el código. Intenta más tarde.")
    return {"message": "Te mandamos un código por WhatsApp."}


@router.post("/verify")
@limiter.limit("10/minute")
async def verify(
    request: Request, response: Response, body: dict,
    db: AsyncSession = Depends(get_db), redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict:
    redis = _need_redis(redis)
    phone = _phone(body.get("phone"))
    await _checked(redis, phone, body.get("code"))
    user = await owner_by_phone(db, phone)
    if user is None:
        raise HTTPException(status_code=404, detail="Ese WhatsApp no tiene un negocio en IaRadio todavía.")
    if user.subscription_status == "suspended":
        raise HTTPException(status_code=403, detail="Cuenta suspendida. Contacta soporte.")
    tokens = await issue_session(user, response, redis)
    capture_event("user_login", user_id=user.id, properties={"via": "whatsapp"})
    return {**tokens.model_dump(), "slug": user.slug or ""}


@router.post("/signup")
@limiter.limit("5/hour")
async def signup(
    request: Request, response: Response, body: dict,
    db: AsyncSession = Depends(get_db), redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict:
    redis = _need_redis(redis)
    phone = _phone(body.get("phone"))
    name = " ".join(str(body.get("name") or "").split())[:120]
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="¿Cómo se llama tu negocio?")
    await _checked(redis, phone, body.get("code"))

    user = await owner_by_phone(db, phone)
    created = user is None
    if created:
        profile = body.get("profile") if isinstance(body.get("profile"), dict) else {}
        user = await create_owner(db, phone=phone, name=name, profile=profile, color=body.get("color"))
        capture_event("user_registered", user_id=user.id, properties={"via": "chat", "business_name": name})
    tokens = await issue_session(user, response, redis)
    return {**tokens.model_dump(), "slug": user.slug or "", "created": created, "business_name": user.business_name or ""}
