"""
Twilio voice verification webhook — answers and records incoming calls.
Used for Meta WhatsApp Business number verification.
"""
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter()


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
    """Callback after recording completes — just hang up."""
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Hangup/>
</Response>"""
    return PlainTextResponse(content=twiml, media_type="application/xml")
