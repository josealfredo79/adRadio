"""Tests for lead scoring and file text extraction utilities."""

from app.services.lead_score import calculate_lead_score
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
