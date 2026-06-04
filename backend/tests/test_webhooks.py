"""Tests for webhook handlers."""

import pytest
from app.api.v1.webhooks_pkg.lead_score import calculate_lead_score
from app.api.v1.webhooks_pkg.twilio_incoming import _validate_twilio_signature
from app.workers.task_helpers.extract import _extract_text


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
