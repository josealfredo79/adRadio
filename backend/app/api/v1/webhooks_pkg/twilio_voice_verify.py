"""
Twilio voice verification webhook — answers incoming calls with TwiML.
Used for Meta WhatsApp Business number verification.
"""
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter()


@router.post("/twilio/voice-verify", response_class=PlainTextResponse)
async def twilio_voice_verify(request: Request):
    """Answer voice call and play a silence tone — allows Meta to verify the number."""
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Miguel"></Say>
  <Pause length="1"/>
  <Hangup/>
</Response>"""
    return PlainTextResponse(content=twiml, media_type="application/xml")
