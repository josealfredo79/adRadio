"""
Twilio voice verification webhook — answers and records incoming calls.
Used for Meta WhatsApp Business number verification.

Also exposes a self-refreshing listen page + audio proxy so the recording
can be played from a stable URL without navigating the Twilio console
(which is a SPA and 404s on direct/deep-linked routes) or downloading the
file manually — both too slow against Meta's ~2 minute verification window.
"""
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from app.config import settings
from app.core.redis import get_redis_optional

logger = logging.getLogger(__name__)

router = APIRouter()

REDIS_KEY = "twilio:voice_verify:latest_recording_sid"


@router.post("/twilio/voice-verify", response_class=PlainTextResponse)
async def twilio_voice_verify(request: Request):
    """Answer voice call, record it (to capture Meta verification code), then hang up."""
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Record maxLength="30" playBeep="false" action="/api/v1/webhooks/twilio/voice-verify-status"/>
</Response>"""
    return PlainTextResponse(content=twiml, media_type="application/xml")


@router.post("/twilio/voice-verify-status", response_class=PlainTextResponse)
async def twilio_voice_verify_status(request: Request):
    """Callback after recording completes — stash the recording SID, then hang up."""
    form = await request.form()
    recording_sid = form.get("RecordingSid")
    if recording_sid:
        redis = await get_redis_optional()
        if redis:
            await redis.set(REDIS_KEY, recording_sid, ex=3600)
        logger.info("Grabación de verificación de voz lista: %s", recording_sid)

    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Hangup/>
</Response>"""
    return PlainTextResponse(content=twiml, media_type="application/xml")


@router.get("/twilio/voice-verify-listen", response_class=HTMLResponse)
async def twilio_voice_verify_listen(token: str = Query(...)):
    """Self-refreshing page with an audio player for the latest verification call recording."""
    if not settings.VOICE_VERIFY_TOKEN or token != settings.VOICE_VERIFY_TOKEN:
        raise HTTPException(status_code=404)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="3">
<title>Verificación de voz</title>
<style>
body {{ font-family: sans-serif; background: #111; color: #eee; text-align: center; padding: 3rem 1rem; }}
audio {{ width: 100%; max-width: 400px; margin-top: 1.5rem; }}
</style>
</head>
<body>
<h2>Última llamada de verificación</h2>
<p>Esta página se recarga sola cada 3 segundos hasta que llegue la grabación.</p>
<audio controls autoplay src="/api/v1/webhooks/twilio/voice-verify-audio?token={token}"></audio>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/twilio/voice-verify-audio")
async def twilio_voice_verify_audio(token: str = Query(...)):
    """Proxies the latest recording's mp3 from Twilio (Twilio requires Basic Auth we don't want in the browser)."""
    if not settings.VOICE_VERIFY_TOKEN or token != settings.VOICE_VERIFY_TOKEN:
        raise HTTPException(status_code=404)

    redis = await get_redis_optional()
    recording_sid = await redis.get(REDIS_KEY) if redis else None
    if not recording_sid:
        raise HTTPException(status_code=404, detail="Aún no hay grabación disponible")

    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Recordings/{recording_sid}.mp3"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            follow_redirects=True,
            timeout=15,
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="No se pudo descargar la grabación de Twilio")

    return Response(content=resp.content, media_type="audio/mpeg")
