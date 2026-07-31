"""Tests for matches_handoff_intent — the backup regex (ported from
vocero-crm's src/server/ai/handoff.ts) that detects a customer explicitly
asking to talk to a human, independent of whatever Claude decides to say."""
import pytest

from app.services.handoff_service import matches_handoff_intent


class TestMatchesHandoffIntent:
    @pytest.mark.parametrize("text", [
        "quiero hablar con un asesor",
        "necesito hablar con una persona por favor",
        "me puedes comunicar con un humano",
        "quiero contactar a alguien del equipo",
        "un asesor porfa",
        "necesito atención humana",
        "ATENCIÓN HUMANA YA",
        "podrías contactarme con una persona real",
    ])
    def test_explicit_human_requests_match(self, text):
        assert matches_handoff_intent(text) is True

    @pytest.mark.parametrize("text", [
        "somos 4 personas para la cena de mañana",
        "¿cuánto cuesta el pastel de 4 personas?",
        "hola, buenos días",
        "quiero saber los precios",
        "hablar bien de ustedes es fácil, me encanta el servicio",
        "",
    ])
    def test_unrelated_messages_do_not_match(self, text):
        assert matches_handoff_intent(text) is False

    def test_none_does_not_match(self):
        assert matches_handoff_intent(None) is False
