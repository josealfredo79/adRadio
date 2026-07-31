"""Tests for detect_plan_purchase_intent — tightened after a real production
bug: the old ~40-word keyword list matched on bare words like "precio",
"comprar", "contratar", "pagar", so a business's own customer asking about
THEIR product/price got misread as wanting to buy an IaRadio subscription
plan and got a "¿Confirmas que quieres el Plan Starter?" reply instead of
an answer to their actual question."""
import pytest

from app.services.claude_service import detect_plan_purchase_intent


class TestRealFalsePositiveIsFixed:
    """The exact message that surfaced this bug in production."""

    @pytest.mark.parametrize("text", [
        "¿cuánto cuesta el pastel de 4 personas?",
        "cuanto cuesta el pastel de 4 personas",
        "¿cuál es el precio del pan integral?",
        "quiero comprar 2 pasteles de chocolate",
        "¿puedo pagar con tarjeta?",
        "necesito contratar el servicio de banquete para mi evento",
        "¿tienen planes de comida para la semana?",
        "recomiéndame algo dulce",
        "¿está más barato el paquete grande?",
    ])
    def test_ordinary_business_questions_do_not_match(self, text):
        assert detect_plan_purchase_intent(text) is None


class TestGenuinePlanIntentStillMatches:
    @pytest.mark.parametrize("text,expected", [
        ("quiero el plan growth", "growth"),
        ("quiero el starter", "starter"),
        ("me interesa el pro", "pro"),
        ("quiero contratar el plan business", "business"),
        ("dame el growth", "growth"),
        ("me voy con el pro", "pro"),
        ("quiero comprar el plan enterprise", "enterprise"),
    ])
    def test_tier_plus_intent_verb_matches(self, text, expected):
        assert detect_plan_purchase_intent(text) == expected

    def test_mentioning_platform_name_with_tier_matches(self):
        assert detect_plan_purchase_intent("quiero el starter de iaradio") == "starter"

    def test_mentioning_platform_name_without_tier_defaults_to_starter(self):
        assert detect_plan_purchase_intent("quiero contratar iaradio") == "starter"

    @pytest.mark.parametrize("text", [
        "me interesa anunciarme",
        "quiero anunciarme",
        "quiero promocionar mi negocio",
    ])
    def test_advertising_intent_phrases_match(self, text):
        assert detect_plan_purchase_intent(text) == "starter"


class TestBareTierNameAloneDoesNotMatch:
    def test_tier_name_without_intent_verb_or_platform_mention_is_ambiguous(self):
        """'pro' or 'starter' appearing incidentally (e.g. describing a
        product tier of the BUSINESS itself) shouldn't trigger without a
        clearer signal."""
        assert detect_plan_purchase_intent("el nivel pro de mi membresía de gym") is None
