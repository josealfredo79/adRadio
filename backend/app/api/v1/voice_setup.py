"""Configurar el bot por voz — /api/v1/voice-setup (ver services/voice_setup.py).

Dos pasos para que nada se guarde sin que el dueño lo vea:
1. POST /listen: audio (o texto, si no puede usar el micrófono) → borrador.
   Con `draft`, el audio es una corrección sobre ese borrador.
2. POST /apply: el borrador que el dueño aprobó → bot configurado.
"""
import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limiter import limiter
from app.database import get_db
from app.models.product import Product
from app.models.user import User
from app.services.voice_setup import (
    extract_profile,
    render_hours,
    render_instructions,
    sanitize_profile,
)
from app.services.whisper_service import transcribe_audio_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice-setup", tags=["voice-setup"])

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # ~5 min de voz comprimida sobra con esto
MAX_TEXT = 6000


def _out(profile: dict, transcript: str, user: User) -> dict:
    return {
        "transcript": transcript,
        "profile": profile,
        "hours_text": render_hours(profile["business_hours"]),
        "instructions_preview": render_instructions(profile),
        "replaces_existing_instructions": bool(user.bot_instructions),
    }


@router.post("/listen")
@limiter.limit("10/minute")
async def listen(
    request: Request,
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
    draft: str | None = Form(None),
    current_user: User = Depends(get_current_user),
) -> dict:
    if audio is not None:
        data = await audio.read()
        if not data:
            raise HTTPException(status_code=400, detail="El audio llegó vacío. Intenta grabar de nuevo.")
        if len(data) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="El audio es muy largo. Intenta con menos de 5 minutos.")
        content_type = (audio.content_type or "audio/webm").split(";")[0]
        transcript = await transcribe_audio_bytes(data, content_type)
        if not transcript:
            raise HTTPException(
                status_code=422,
                detail="No alcancé a escuchar bien. Intenta de nuevo cerca del celular, o escríbelo.",
            )
    elif text and text.strip():
        transcript = text.strip()[:MAX_TEXT]
    else:
        raise HTTPException(status_code=400, detail="Mándame un audio o escríbelo")

    current = None
    if draft:
        try:
            current = json.loads(draft)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Borrador inválido")

    try:
        profile = await extract_profile(transcript, current, current_user.business_name or "")
    except Exception:
        logger.exception("[VOICE-SETUP] extraction failed user=%s", current_user.id)
        raise HTTPException(
            status_code=502, detail="No pude ordenar lo que me contaste. Intenta de nuevo en un momento.",
        )
    return _out(profile, transcript, current_user)


class ApplyBody(BaseModel):
    profile: dict


@router.post("/apply")
async def apply(
    body: ApplyBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Guarda lo que el dueño aprobó: instrucciones del bot, horario (también
    lo usa la agenda de citas), giro/ciudad y los servicios como productos del
    catálogo (crea los nuevos; actualiza el precio de los que ya existían)."""
    p = sanitize_profile(body.profile)
    instructions = render_instructions(p)
    if not instructions:
        raise HTTPException(status_code=400, detail="No hay nada que guardar todavía")

    current_user.bot_instructions = instructions
    if p["business_hours"]:
        current_user.business_hours = p["business_hours"]
    if p["business_category"]:
        current_user.business_category = p["business_category"]
    if p["city"]:
        current_user.city = p["city"]

    existing = {
        prod.name.strip().lower(): prod
        for prod in (await db.execute(select(Product).where(Product.advertiser_id == current_user.id))).scalars().all()
    }
    created = updated = 0
    for s in p["services"]:
        prod = existing.get(s["name"].lower())
        if prod is None:
            db.add(Product(
                advertiser_id=current_user.id, name=s["name"], price=s["price"],
                description=s["description"], active=True,
            ))
            created += 1
        elif s["price"] is not None and (prod.price is None or float(prod.price) != s["price"]):
            prod.price = s["price"]
            updated += 1

    await db.commit()
    logger.info("[VOICE-SETUP] applied user=%s products +%s ~%s", current_user.id, created, updated)
    return {
        "instructions_chars": len(instructions),
        "hours_set": bool(p["business_hours"]),
        "products_created": created,
        "products_updated": updated,
    }
