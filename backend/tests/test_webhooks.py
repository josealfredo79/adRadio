"""Tests for webhook handlers."""

import os
from unittest.mock import AsyncMock, patch

import pytest
from app.api.v1.webhooks_pkg.lead_score import calculate_lead_score
from app.api.v1.webhooks_pkg.twilio_incoming import _validate_twilio_signature
from app.workers.task_helpers.extract import _extract_text

HAS_DB = bool(os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL"))

try:
    from app.main import app
    HAS_APP = True
except Exception:
    HAS_APP = False
    app = None

db_reason = "Requiere base de datos (TEST_DATABASE_URL o DATABASE_URL)"


class TestLeadScore:
    def test_hot_keywords(self):
        assert calculate_lead_score("quiero comprar un producto", 0) == "hot"
        assert calculate_lead_score("cuánto cuesta?", 0) == "hot"
        assert calculate_lead_score("precio por favor", 0) == "hot"
        assert calculate_lead_score("oferta especial", 0) == "hot"

    def test_warm_keywords(self):
        assert calculate_lead_score("quisiera información", 0) == "warm"
        assert calculate_lead_score("estoy pensando en", 0) == "warm"

    def test_cold_keywords(self):
        assert calculate_lead_score("hola", 0) == "cold"
        assert calculate_lead_score("gracias", 0) == "cold"
        assert calculate_lead_score("ok", 0) == "cold"

    def test_message_count_three_plus(self):
        assert calculate_lead_score("hola", 3) == "warm"
        assert calculate_lead_score("ok", 5) == "warm"

    def test_short_message_cold(self):
        assert calculate_lead_score("si", 0) == "cold"
        assert calculate_lead_score("no", 0) == "cold"

    def test_default_warm(self):
        assert calculate_lead_score("esto es un mensaje normal y corriente", 0) == "warm"


class TestTwilioSignature:
    def test_validate_signature_valid(self):
        import hashlib
        import hmac
        import base64

        from app.config import settings
        request_url = "https://example.com/webhook"
        params = {"From": "whatsapp:+1234567890", "Body": "Hello"}
        sorted_params = "".join(f"{k}{v}" for k, v in sorted(params.items()))
        s = request_url + sorted_params
        mac = hmac.new(
            settings.TWILIO_AUTH_TOKEN.encode("utf-8"),
            s.encode("utf-8"),
            hashlib.sha1,
        )
        valid_sig = base64.b64encode(mac.digest()).decode()

        assert _validate_twilio_signature(request_url, params, valid_sig) is True

    def test_validate_signature_invalid(self):
        assert _validate_twilio_signature("https://example.com", {}, "invalid_sig") is False


class TestTextExtraction:
    def test_extract_txt(self):
        content = b"Hola mundo\nEsto es un texto"
        result = _extract_text(content, "txt")
        assert result == "Hola mundo\nEsto es un texto"

    def test_extract_empty_type(self):
        result = _extract_text(b"something", "unknown")
        assert result == ""

    def test_extract_empty_audio_no_key(self):
        result = _extract_text(b"audio_data", "audio")
        assert result == ""


class TestSharedNumberBotReply:
    """Regression tests: messages to IaRadio's shared WhatsApp number (no
    advertiser owns the contact) must be answered by Claude using the real
    message content — not with a static canned welcome repeated forever."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
    async def test_replies_use_real_message_not_static_text(self):
        from httpx import AsyncClient, ASGITransport
        from app.config import settings

        shared_number = settings.TWILIO_WHATSAPP_NUMBER.replace("whatsapp:", "")
        calls = []

        async def fake_generate_bot_response(**kwargs):
            calls.append(kwargs["user_message"])
            return f"respuesta a: {kwargs['user_message']}"

        transport = ASGITransport(app=app)
        with patch(
            "app.api.v1.webhooks_pkg.twilio_incoming.generate_bot_response",
            fake_generate_bot_response,
        ), patch(
            "app.api.v1.webhooks_pkg.twilio_incoming._send_wa",
            AsyncMock(return_value=("SID123", None)),
        ) as send_mock, patch(
            "app.api.v1.webhooks_pkg.twilio_incoming.get_redis_optional",
            AsyncMock(return_value=None),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                messages = ["Que servicios ofreces", "Necesito info", "Que servicios ofreces"]
                for i, msg in enumerate(messages):
                    resp = await c.post(
                        "/api/v1/webhooks/twilio/incoming",
                        data={
                            "From": "whatsapp:+5219511112222",
                            "To": f"whatsapp:{shared_number}",
                            "Body": msg,
                            "MessageSid": f"SMtest-shared-{i}",
                            "NumMedia": "0",
                        },
                    )
                    assert resp.status_code == 200

        # The bot must receive the actual message text each time, never a
        # hardcoded fallback that ignores what the user typed.
        assert calls == messages
        replies_sent = [call.args[1] for call in send_mock.call_args_list]
        assert replies_sent == [f"respuesta a: {m}" for m in messages]
