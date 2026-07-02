"""Public demo chat endpoint — no auth required."""
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis as AsyncRedis

from app.core.redis import get_redis_optional
from app.core.rate_limiter import limiter
from app.services.claude_service import generate_bot_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

DEMO_BUSINESS_NAME = "IaRadio"
DEMO_BOT_NAME = "Alex"
DEMO_BOT_PERSONALITY = (
    "Soy un asistente de IaRadio, una plataforma SaaS que ayuda a "
    "pequeños negocios y anunciantes a automatizar sus ventas por "
    "WhatsApp con inteligencia artificial. Me encanta explicar cómo "
    "IaRadio puede transformar la forma en que atienden clientes."
)

DEMO_CONTEXT = """
IaRadio es una plataforma SaaS para pequeños negocios y anunciantes.

PLANES:
- Starter: $299/mes, 500 mensajes, chatbot IA, panel básico
- Growth: $599/mes, 2000 mensajes, chatbot + RAG + cuñas de radio
- Pro: $999/mes, 5000 mensajes, secuencias, API WhatsApp Business
- Business: $1,999/mes, mensajes ilimitados, todo incluido + white-label

CARACTERÍSTICAS PRINCIPALES:
- Chatbot IA con Claude que atiende clientes 24/7
- Base de conocimiento RAG (la IA aprende de tu negocio)
- Detección y toma de pedidos automática
- Gestión de citas con recordatorios
- Campañas de marketing masivo por WhatsApp
- Cuñas de radio generadas con IA (texto a voz)
- Panel de control con analytics en tiempo real
- Cupones de descuento y automatizaciones
- Integración con Stripe, Google Calendar
- Widget de WhatsApp embebible para tu web
- Importación de contactos desde CSV

IDIOMA: Español (Latinoamérica)
"""

REDIS_PREFIX = "chat_demo:"
REDIS_TTL = 1800
MAX_HISTORY = 20


@router.post("/demo")
@limiter.limit("5/minute")
async def demo_chat(
    request: Request,
    body: dict,
    redis: AsyncRedis | None = Depends(get_redis_optional),
) -> dict:
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    if len(message) > 500:
        raise HTTPException(status_code=400, detail="message too long (max 500 chars)")

    session_id = body.get("session_id") or str(uuid.uuid4())
    history: list[dict] = []

    if redis:
        key = f"{REDIS_PREFIX}{session_id}"
        raw = await redis.get(key)
        if raw:
            try:
                history = json.loads(raw)
            except json.JSONDecodeError:
                history = []

    try:
        reply = await generate_bot_response(
            advertiser_context=DEMO_CONTEXT,
            conversation_history=history,
            user_message=message,
            business_name=DEMO_BUSINESS_NAME,
            bot_name=DEMO_BOT_NAME,
            bot_personality=DEMO_BOT_PERSONALITY,
        )
    except Exception as e:
        logger.error("[DEMO_CHAT] Claude error: %s", e, exc_info=True)
        reply = (
            "¡Hola! Soy Alex de IaRadio. 🎙️\n\n"
            "Somos una plataforma que automatiza las ventas por WhatsApp con IA. "
            "Ayudamos a pequeños negocios a atender clientes 24/7, "
            "enviar campañas y generar más ventas.\n\n"
            "¿Te gustaría saber más sobre los planes o cómo funciona? 😊"
        )

    if redis:
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})
        history = history[-MAX_HISTORY:]
        await redis.setex(key, REDIS_TTL, json.dumps(history))

    return {"reply": reply, "session_id": session_id}
