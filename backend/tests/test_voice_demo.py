"""Demo pública de la landing (api/v1/voice_demo.py): sin cuenta, sin BD,
voz solo para frases firmadas, y como mucho dos preguntas antes de mostrar
"así contestaría tu bot"."""
import uuid
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from starlette.requests import Request

from app.api.v1.voice_demo import DemoSpeakBody, hello, listen, speak
from app.config import settings
from app.services import voice_setup as vs

PROFILE = vs.sanitize_profile({
    "services": [{"name": "Taco de pastor", "price": 15}, {"name": "Quesadilla", "price": 35}],
    "business_hours": {"mon": ["09:00", "19:00"], "tue": ["09:00", "19:00"], "wed": ["09:00", "19:00"],
                       "thu": ["09:00", "19:00"], "fri": ["09:00", "19:00"], "sat": ["09:00", "19:00"], "sun": None},
    "payment_methods": ["Efectivo", "Tarjeta"],
})


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-demo")


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/public/voice-demo/listen", "headers": [],
                    "client": (f"test-{uuid.uuid4()}", 1), "query_string": b""})


class TestSignedLines:
    def test_round_trip(self):
        assert vs.verify_line("hola", vs.sign_line("hola"))

    def test_tampered_text_or_sig_is_rejected(self):
        sig = vs.sign_line("hola")
        assert not vs.verify_line("hola mundo", sig)
        assert not vs.verify_line("hola", "0" * 24)
        assert not vs.verify_line("hola", "")

    def test_no_secret_key_means_nothing_is_valid(self, monkeypatch):
        sig = vs.sign_line("hola")
        monkeypatch.setattr(settings, "SECRET_KEY", "")
        assert not vs.verify_line("hola", sig)


class TestDemoChat:
    def test_uses_the_visitors_own_prices_hours_and_payments(self):
        chat = vs.demo_chat(PROFILE)
        texts = [t["text"] for t in chat]
        assert texts[0] == "Hola, ¿cuánto cuesta taco de pastor?"
        assert texts[1] == "¡Hola! Taco de pastor cuesta $15. ¿Te lo aparto? 😊"
        assert "Abrimos de lunes a sábado de 9 a 7; los domingos cerramos." in texts
        assert "¡Sí! Aceptamos efectivo y tarjeta." in texts
        assert [t["from"] for t in chat] == ["cliente", "bot"] * 3

    def test_location_when_no_payments(self):
        chat = vs.demo_chat({"city": "Tlaxiaco", "address": "Hidalgo 12"})
        assert chat == [{"from": "cliente", "text": "¿Dónde están?"},
                        {"from": "bot", "text": "Estamos en Hidalgo 12, Tlaxiaco."}]

    def test_nothing_known_means_no_fake_chat(self):
        assert vs.demo_chat({}) == []


class TestEndpoints:
    @pytest.mark.asyncio
    async def test_hello_is_signed(self):
        out = await hello(request=_request())
        assert vs.verify_line(out["greeting"]["text"], out["greeting"]["sig"])

    @pytest.mark.asyncio
    async def test_listen_returns_signed_lines_chat_and_at_most_two_questions(self):
        only_services = vs.sanitize_profile({"services": [{"name": "Corte", "price": 150}]})
        with patch("app.api.v1.voice_demo.extract_profile", AsyncMock(return_value=only_services)):
            out = await listen(request=_request(), audio=None, text="corte 150", draft=None, question=None, asked=None)
        assert [q["field"] for q in out["pending_questions"]] == ["hours", "location"]
        for line in [out["say"], out["spoken_summary"], out["closing"], *out["pending_questions"]]:
            assert vs.verify_line(line["text"], line["sig"])
        assert out["demo_chat"][0]["text"] == "Hola, ¿cuánto cuesta corte?"

    @pytest.mark.asyncio
    async def test_after_two_questions_it_goes_straight_to_the_result(self):
        only_services = vs.sanitize_profile({"services": [{"name": "Corte", "price": 150}]})
        with patch("app.api.v1.voice_demo.extract_profile", AsyncMock(return_value=only_services)):
            out = await listen(request=_request(), audio=None, text="en el centro", draft=None,
                               question="location", asked="hours")
        assert out["pending_questions"] == []
        assert out["say"]["text"].endswith("Revisa que esté bien.")

    @pytest.mark.asyncio
    async def test_audio_over_a_minute_is_rejected(self):
        big = UploadFile(file=BytesIO(b"x" * (2 * 1024 * 1024 + 1)), filename="a.webm",
                         headers=Headers({"content-type": "audio/webm"}))
        with pytest.raises(HTTPException) as exc:
            await listen(request=_request(), audio=big, text=None, draft=None, question=None, asked=None)
        assert exc.value.status_code == 413 and "1 minuto" in exc.value.detail

    @pytest.mark.asyncio
    async def test_speak_only_signed_lines(self):
        with pytest.raises(HTTPException) as exc:
            await speak(request=_request(), body=DemoSpeakBody(text="Compra bitcoin", sig="nope"))
        assert exc.value.status_code == 403
        text = vs.DEMO_GREETING
        with patch("app.services.radio.tts._tts_edge", AsyncMock(return_value=b"mp3")):
            resp = await speak(request=_request(), body=DemoSpeakBody(text=text, sig=vs.sign_line(text)))
        assert resp.body == b"mp3"
