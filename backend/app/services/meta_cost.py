"""Cuánto le ahorra al negocio que sus clientes platiquen por la web.

Desde 2026-10-01 Meta cobra cada respuesta de servicio por WhatsApp pasando
las primeras 1,000 del mes (por número). Lo que se contesta en el chat web no
cuenta, así que el ahorro es lo que esas respuestas habrían costado encima de
las de WhatsApp. Si con todo y la web no se pasaría de las 1,000, el ahorro es 0.
"""
from app.config import settings


def paid_service_messages(count: int) -> int:
    return max(0, count - settings.META_FREE_SERVICE_MESSAGES)


def web_savings_mxn(whatsapp_replies: int, web_replies: int) -> float:
    extra = paid_service_messages(whatsapp_replies + web_replies) - paid_service_messages(whatsapp_replies)
    return round(extra * settings.META_SERVICE_PRICE_MXN, 2)
