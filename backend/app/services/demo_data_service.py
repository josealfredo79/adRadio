"""
Demo Data Seeding Service — creates sample data for new advertisers
so they see a populated dashboard after email verification.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SAMPLE_CONTACTS = [
    {
        "name": "María García",
        "phone": "+5215512345601",
        "email": "maria@example.com",
        "city": "CDMX",
        "tags": ["interesado", "presupuesto"],
    },
    {
        "name": "Carlos López",
        "phone": "+5215512345602",
        "email": "carlos@example.com",
        "city": "Guadalajara",
        "tags": ["cliente_recurrente"],
    },
    {
        "name": "Ana Martínez",
        "phone": "+5215512345603",
        "email": "ana@example.com",
        "city": "Monterrey",
        "tags": ["nuevo", "promocion"],
    },
]

SAMPLE_KB_TEXT = (
    "IaRadio es una plataforma de marketing digital que permite a las empresas "
    "enviar campañas de WhatsApp automatizadas con inteligencia artificial. "
    "Nuestra plataforma ofrece:\n\n"
    "- Campañas inteligentes con segmentación por etiquetas\n"
    "- Generación de cuñas de radio con IA\n"
    "- Chatbot con respuestas automáticas personalizadas\n"
    "- Coupons y promociones\n"
    "- Panel de control con estadísticas en tiempo real\n"
    "- Widget de WhatsApp para sitios web\n\n"
    "Los horarios de atención son de lunes a viernes de 9:00 a 18:00 (hora CDMX). "
    "El soporte técnico responde en menos de 2 horas hábiles."
)


async def seed_demo_data(advertiser_id: uuid.UUID, business_name: str, db: AsyncSession) -> None:
    """
    Create sample contacts, a draft campaign, and a knowledge-base entry
    so new advertisers see a non-empty dashboard immediately.
    """
    from app.models.contact import Contact
    from app.models.campaign import Campaign
    from app.models.knowledge_base import KnowledgeBase

    try:
        # ── 1. Sample contacts ────────────────────────────────────────────
        for data in SAMPLE_CONTACTS:
            contact = Contact(
                advertiser_id=advertiser_id,
                name=data["name"],
                phone=data["phone"],
                email=data["email"],
                city=data["city"],
                tags=data["tags"],
                source="manual",
            )
            db.add(contact)

        # ── 2. Sample campaign (draft) ────────────────────────────────────
        campaign = Campaign(
            advertiser_id=advertiser_id,
            name=f"¡Bienvenido a {business_name}! 🎉",
            type="promo",
            message_text=(
                "¡Hola {name}! 👋\n\n"
                "Gracias por contactar con {business_name}. "
                "Tenemos promociones especiales para ti esta semana.\n\n"
                "Visítanos en:\n📍 {city}\n\n"
                "Responde *info* para más detalles."
            ),
            segment={"tags": []},
            schedule={
                "start_date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "timezone": "America/Mexico_City",
            },
            ab_test={"enabled": False},
            status="draft",
        )
        db.add(campaign)

        # ── 3. Sample knowledge-base entry ────────────────────────────────
        kb = KnowledgeBase(
            advertiser_id=advertiser_id,
            filename="demo-informacion.txt",
            file_type="txt",
            raw_text=SAMPLE_KB_TEXT,
            processing_status="done",
            is_active=True,
        )
        db.add(kb)

        await db.commit()
        logger.info("[DEMO] Seeded data for advertiser %s (%s)", advertiser_id, business_name)

    except Exception as e:
        logger.error("[DEMO] Failed to seed demo data for %s: %s", advertiser_id, e)
        await db.rollback()
        raise
