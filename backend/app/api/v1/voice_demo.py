"""Demo pública de la landing — /api/v1/public/voice-demo ("Pruébalo en 30 segundos").

Un visitante SIN cuenta le cuenta su negocio a la carita y ve cómo contestaría
su bot. Es la misma plática de "Cuéntale a tu bot" (voice_setup.py), con
candados porque es pública y cada uso cuesta (Whisper + IA):

- Nada se guarda en la BD. El borrador vive en el navegador del visitante y
  se aplica después de registrarse, desde /app/voice-setup.
- Audios de hasta ~1 minuto y límite de usos por IP (uvicorn corre con
  --proxy-headers detrás de Railway, ver start.sh: la IP es la del visitante).
- La voz solo pronuncia frases firmadas por el servidor (sign_line): no es
  un servicio de texto a voz abierto.
"""
import json
import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from app.api.v1.voice_setup import read_transcript
from app.core.rate_limiter import limiter
from app.services.voice_setup import (
    DEMO_CLOSING,
    DEMO_GREETING,
    QUESTION_TEXT,
    demo_chat,
    extract_profile,
    pending_questions,
    sign_line,
    spoken_reply,
    spoken_summary,
    verify_line,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/voice-demo", tags=["voice-demo"])

MAX_DEMO_AUDIO_BYTES = 2 * 1024 * 1024  # ~1 min de voz comprimida (mp4 de iPhone pesa más que webm)
MAX_DEMO_TEXT = 1500


def _line(text: str) -> dict:
    return {"text": text, "sig": sign_line(text)}


@router.get("/hello")
@limiter.limit("30/hour")
async def hello(request: Request) -> dict:
    return {"greeting": _line(DEMO_GREETING)}


@router.post("/listen")
@limiter.limit("12/hour")
async def listen(
    request: Request,
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
    draft: str | None = Form(None),
    question: str | None = Form(None),
    asked: str | None = Form(None),
) -> dict:
    """Una demo completa son 2–3 llamadas (contar + contestar una o dos
    preguntas); 12 por hora alcanza para probar de verdad y frena el abuso."""
    transcript = await read_transcript(audio, text, MAX_DEMO_AUDIO_BYTES, MAX_DEMO_TEXT, "1 minuto")

    current = None
    if draft:
        try:
            current = json.loads(draft)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Borrador inválido")

    try:
        profile = await extract_profile(transcript, current, "", question_text=QUESTION_TEXT.get(question or ""))
    except Exception:
        logger.exception("[VOICE-DEMO] extraction failed")
        raise HTTPException(status_code=502, detail="No pude ordenar lo que me contaste. Intenta de nuevo en un momento.")

    asked_list = [a for a in (asked or "").split(",") if a in QUESTION_TEXT]
    if question in QUESTION_TEXT and question not in asked_list:
        asked_list.append(question)
    # En la demo bastan dos preguntas: el chiste es llegar rápido a "así contestaría tu bot".
    pending = pending_questions(profile, asked_list)[: max(0, 2 - len(asked_list))]
    say = spoken_reply(profile, current, pending[0] if pending else None)
    return {
        "transcript": transcript,
        "profile": profile,
        "say": _line(say),
        "pending_questions": [{"field": q["field"], **_line(q["text"])} for q in pending],
        "spoken_summary": _line(spoken_summary(profile)),
        "demo_chat": demo_chat(profile),
        "closing": _line(DEMO_CLOSING),
    }


class DemoSpeakBody(BaseModel):
    text: str
    sig: str


@router.post("/speak")
@limiter.limit("40/hour")
async def speak(request: Request, body: DemoSpeakBody) -> Response:
    if not verify_line(body.text, body.sig):
        raise HTTPException(status_code=403, detail="Frase no permitida")
    from app.services.radio.tts import _tts_edge

    try:
        audio = await _tts_edge(body.text[:600], "es-MX-DaliaNeural", rate="+0%", pitch="+0Hz")
    except Exception:
        logger.warning("[VOICE-DEMO] TTS failed", exc_info=True)
        raise HTTPException(status_code=503, detail="Voz no disponible")
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})
