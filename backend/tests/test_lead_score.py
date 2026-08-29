"""calculate_lead_score — la intención de compra explícita gana sobre todo,
incluso en hilos largos (antes un `return "warm"` por message_count >= 3 la
tapaba)."""
from app.services.lead_score import calculate_lead_score


def test_hot_keyword_beats_message_count_gate():
    assert calculate_lead_score("quiero comprar ahora", message_count=8) == "hot"
    assert calculate_lead_score("¿cuánto cuesta? lo necesito ya", message_count=20) == "hot"


def test_hot_keyword_on_fresh_conversation():
    assert calculate_lead_score("me interesa el precio", message_count=0) == "hot"


def test_long_thread_without_hot_intent_is_warm():
    assert calculate_lead_score("ah ok gracias", message_count=5) == "warm"


def test_cold_greeting():
    assert calculate_lead_score("hola", message_count=1) == "cold"


def test_warm_keyword():
    assert calculate_lead_score("estoy pensando en info", message_count=1) == "warm"


def test_empty_is_cold():
    assert calculate_lead_score("", message_count=0) == "cold"
