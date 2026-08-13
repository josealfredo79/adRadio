"""Tests for detect_catalog_intent — confirms it fires on real catalog
requests and, critically, does NOT collide with _ORDER_KEYWORDS or
_APPOINTMENT_KEYWORDS (both channels check catalog first, so a false
positive there would swallow real order/appointment messages)."""
import pytest

from app.services.claude_service import (
    _APPOINTMENT_KEYWORDS,
    _ORDER_KEYWORDS,
    detect_appointment_intent,
    detect_catalog_intent,
    detect_order_intent,
)


class TestAppointmentIntentMatches:
    """"una cita" a secas (sin "quiero"/"agendar"/etc.) no hacía match antes
    — un caso real encontrado en producción 2026-08-12: el usuario escribió
    solo "Una cita" y el mensaje cayó al chat genérico en vez del flujo real
    de citas, que alucinó una confirmación falsa sin crear ningún Appointment."""

    @pytest.mark.parametrize("text", [
        "una cita",
        "Una cita",
        "quiero una cita",
        "necesito una cita para mañana",
    ])
    def test_appointment_phrases_match(self, text):
        assert detect_appointment_intent(text) is True


class TestCatalogIntentMatches:
    @pytest.mark.parametrize("text", [
        "¿qué venden?",
        "que venden",
        "muéstrame el catálogo",
        "quiero ver el catalogo",
        "¿tienen menú?",
        "cuál es su menu",
        "qué productos tienen",
        "qué servicios ofrecen",
        "me pasas la lista de precios",
        "carta de precios porfa",
    ])
    def test_catalog_phrases_match(self, text):
        assert detect_catalog_intent(text) is True


class TestCatalogIntentDoesNotMatch:
    @pytest.mark.parametrize("text", [
        "hola buenas tardes",
        "¿cuánto cuesta el pastel de 4 personas?",
        "quiero pedir 2 pizzas",
        "quiero agendar una cita",
    ])
    def test_unrelated_phrases_do_not_match(self, text):
        assert detect_catalog_intent(text) is False


class TestNoCollisionWithOrderOrAppointmentKeywords:
    """detect_catalog_intent is checked BEFORE order/appointment in both
    inbound_pipeline.py and widget.py — if it matched on any real order or
    appointment keyword, it would silently swallow those messages."""

    @pytest.mark.parametrize("kw", sorted(_ORDER_KEYWORDS))
    def test_order_keywords_do_not_trigger_catalog(self, kw):
        assert detect_catalog_intent(kw) is False

    @pytest.mark.parametrize("kw", sorted(_APPOINTMENT_KEYWORDS))
    def test_appointment_keywords_do_not_trigger_catalog(self, kw):
        assert detect_catalog_intent(kw) is False

    @pytest.mark.parametrize("text", [
        "quiero pedir 2 pizzas",
        "quiero agendar una cita para mañana",
    ])
    def test_catalog_does_not_falsely_trigger_on_real_order_or_appointment_messages(self, text):
        assert detect_catalog_intent(text) is False
        # sanity: confirm these really are order/appointment intents in this repo
        assert detect_order_intent(text) is True or detect_appointment_intent(text) is True
