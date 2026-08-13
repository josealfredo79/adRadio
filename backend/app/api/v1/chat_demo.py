"""Public demo chat endpoint — no auth required."""
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis_optional
from app.core.rate_limiter import limiter
from app.database import get_db
from app.services.claude_service import generate_bot_response
from app.api.v1.payments import PLANS

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

# This account holds IaRadio's own plans as real Product rows (added
# 2026-08-13, see product-catalog work same day) — reused here so this demo
# bot can share real, working /p/{advertiser_id}/{product_id} links instead
# of saying "no tengo ese dato a la mano" when a prospect asks for one,
# which is exactly what happened before this fix (confirmed live: a real
# visitor asked for a service link and got refused, even though a real
# link existed for every plan).
DEMO_PLANS_ADVERTISER_EMAIL = "tecnologicotlaxiaco@gmail.com"


def _format_plans() -> str:
    """PLANS (app.api.v1.payments) es la fuente única de verdad de precios."""
    lines = []
    for plan in PLANS.values():
        lines.append(
            f"- {plan['name']}: ${plan['price_mxn']} MXN / ${plan['price_usd']} USD "
            f"por mes, {plan['messages']} mensajes"
        )
    return "\n".join(lines)


async def _format_plan_links(db: AsyncSession) -> str:
    """Real, live links to each plan's shareable product page — see
    DEMO_PLANS_ADVERTISER_EMAIL above for why this account specifically."""
    from app.config import settings
    from app.models.product import Product
    from app.models.user import User

    user_result = await db.execute(select(User).where(User.email == DEMO_PLANS_ADVERTISER_EMAIL))
    user = user_result.scalar_one_or_none()
    if not user:
        return ""

    products_result = await db.execute(
        select(Product)
        .where(Product.advertiser_id == user.id, Product.category == "Planes IaRadio", Product.active.is_(True))
        .order_by(Product.price)
    )
    products = products_result.scalars().all()
    if not products:
        return ""

    lines = [f"- {p.name}: {settings.BASE_URL}/p/{user.id}/{p.id}" for p in products]
    return "\n".join(lines)


def _build_demo_context(plan_links: str) -> str:
    links_block = (
        f"\n\nLINKS REALES DE CADA PLAN (usa EXACTAMENTE estos si te piden un link — nunca inventes uno):\n{plan_links}"
        if plan_links
        else ""
    )
    return f"""
IaRadio es una plataforma SaaS para pequeños negocios y anunciantes.

PLANES:
{_format_plans()}
{links_block}

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
    db: AsyncSession = Depends(get_db),
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
        plan_links = await _format_plan_links(db)
    except Exception:
        logger.warning("[DEMO_CHAT] Failed to load real plan links", exc_info=True)
        plan_links = ""

    try:
        reply = await generate_bot_response(
            advertiser_context=_build_demo_context(plan_links),
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
