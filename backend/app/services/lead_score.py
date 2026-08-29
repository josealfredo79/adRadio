"""
Lead scoring utilities for incoming WhatsApp messages.
"""

HOT_KEYWORDS = [
    "comprar", "precio", "ya", "urgente", "ahora", "quiero", "necesito",
    "pedir", "ordenar", "apartar", "reservar", "cuánto", "costo", "tarifa",
    "promo", "descuento", "oferta",
]
WARM_KEYWORDS = [
    "quizás", "creo", "pensando", "ver", "info", "consultar", "preguntar",
    "saber", "dime", "mandar", "enviar", "详细信息", "cuál", "cómo",
]
COLD_KEYWORDS = [
    "hola", "buenos", "buenas", "saludos", "gracias", "ok", "si", "sí",
    "no", "hi", "hello",
]


def calculate_lead_score(body_text: str, message_count: int) -> str | None:
    """Calculate lead score based on message content and conversation history."""
    text_lower = body_text.lower().strip()

    # Intención de compra explícita gana sobre todo — incluso en un hilo largo,
    # un "quiero comprar ahora" es hot, no warm.
    if any(kw in text_lower for kw in HOT_KEYWORDS):
        return "hot"

    if message_count >= 3:
        return "warm"

    if any(kw in text_lower for kw in WARM_KEYWORDS):
        return "warm"

    if any(kw in text_lower for kw in COLD_KEYWORDS) and len(text_lower) < 15:
        return "cold"

    if len(text_lower) < 5:
        return "cold"

    return "warm"
