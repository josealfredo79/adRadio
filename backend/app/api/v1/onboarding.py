"""Alta en el chat de IaRadio — /api/v1/public/onboarding

Un dueño SIN cuenta le cuenta su negocio a radiecito dentro del chat de
IaRadio y ve su página construirse en una tarjeta. Nada se guarda hasta que
publica confirmando su WhatsApp (auth/whatsapp/signup): el borrador vive en
su navegador.

- POST /listen  nota de voz o texto (+ borrador) → perfil ordenado (nombre,
                giro, ciudad, horario, productos con precio).
- POST /try     una pregunta de "cliente" → lo que contestaría su asistente
                con ese borrador, con el mismo modelo que el bot real.

Públicos y cada uso cuesta (Whisper + IA): topes por IP como la demo de voz.
"""
import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.voice_setup import read_transcript
from app.core.rate_limiter import limiter
from app.database import get_db
from app.models.user import User
from app.services.copilot_service import parse_spoken_yes_no
from app.services.voice_setup import (
    extract_profile,
    render_instructions,
    sanitize_profile,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/onboarding", tags=["onboarding"])

MAX_AUDIO_BYTES = 2 * 1024 * 1024  # ~1 min de voz
MAX_TEXT = 1500


@router.post("/listen")
@limiter.limit("40/hour")
async def listen(
    request: Request,
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
    draft: str | None = Form(None),
    question: str | None = Form(None),
    yes_no: bool = Form(False),
) -> dict:
    """`question`: lo que radiecito le acaba de preguntar ("¿Cómo se llama tu
    negocio?"), para que un "Tacos El Güero" suelto se entienda como nombre
    y un "es de venta de celulares" como giro.

    `yes_no`: lo que preguntó es "¿Es correcto?". Un sí o un no corto se
    contesta como `answer` sin ordenar nada; "no, es Tacos Pepe" es una
    corrección y se ordena como cualquier respuesta."""
    transcript = await read_transcript(audio, text, MAX_AUDIO_BYTES, MAX_TEXT, "1 minuto")
    if yes_no:
        said = parse_spoken_yes_no(transcript)
        if said is True or (said is False and len(transcript.split()) <= 2):
            return {"transcript": transcript, "answer": "yes" if said else "no", "profile": {}}
        question = None
    current = None
    if draft:
        try:
            current = json.loads(draft)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Borrador inválido")
    try:
        profile = await extract_profile(transcript, current, question_text=(question or "")[:200] or None)
    except Exception:
        logger.exception("[ONBOARDING] extraction failed")
        raise HTTPException(status_code=502, detail="No pude ordenar lo que me contaste. Intenta de nuevo en un momento.")
    return {"transcript": transcript, "profile": profile}


class TryBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    profile: dict
    question: str = Field(min_length=1, max_length=300)


@router.post("/try")
@limiter.limit("20/hour")
async def try_assistant(request: Request, body: TryBody) -> dict:
    from app.services.claude_service import generate_bot_response

    profile = sanitize_profile(body.profile)
    try:
        answer = await generate_bot_response(
            advertiser_context="",
            conversation_history=[],
            user_message=body.question,
            business_name=body.name,
            bot_instructions=render_instructions(profile) or None,
            economy=True,
        )
    except Exception:
        logger.exception("[ONBOARDING] try failed")
        raise HTTPException(status_code=502, detail="Tu asistente no pudo contestar ahorita. Intenta de nuevo.")
    return {"answer": answer}


class ApplyBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    profile: dict
    color: str | None = None


@router.post("/apply")
@limiter.limit("30/hour")
async def apply_for_owner(
    request: Request,
    body: ApplyBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """El mismo alta, desde el panel de un dueño que ya inició sesión (se
    registró con correo): sin WhatsApp ni código, se guarda en su cuenta."""
    from app.services.owner_signup import apply_to_owner

    if current_user.role != "advertiser":
        raise HTTPException(status_code=403, detail="Solo los negocios pueden armar su página.")
    user = await apply_to_owner(db, current_user, name=" ".join(body.name.split()), profile=body.profile, color=body.color)
    return {"slug": user.slug or "", "business_name": user.business_name or ""}
