"""
Template seeds router — /api/v1/templates/seeds
Pre-built templates that users can browse and import.
"""
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.template import MessageTemplate
from app.models.user import User

router = APIRouter(prefix="/templates", tags=["templates"])

SEED_TEMPLATES = [
    {"name": "Bienvenida", "category": "Bienvenida", "content": "¡Hola {{nombre}}! Gracias por contactar a {{business_name}}. Estamos aquí para ayudarte. ¿En qué podemos servirte hoy?"},
    {"name": "Promoción general", "category": "Promoción", "content": "¡Hola {{nombre}}! {{business_name}} tiene una oferta especial para ti. Válida hasta agotar existencias. ¡Aprovecha!"},
    {"name": "Recordatorio de cita", "category": "Recordatorio", "content": "Recordatorio {{nombre}}: Tienes una cita con {{business_name}} mañana. Confirma tu asistencia respondiendo este mensaje."},
    {"name": "Seguimiento post-venta", "category": "Seguimiento", "content": "Hola {{nombre}}, ¿cómo te fue con tu compra en {{business_name}}? Nos importa tu opinión. ¡Gracias por preferirnos!"},
    {"name": "Oferta por tiempo limitado", "category": "Oferta", "content": "🔥 Oferta exclusiva {{nombre}}! {{business_name}} te ofrece un descuento especial solo por hoy. Pide más información."},
    {"name": "Cumpleaños", "category": "Cumpleaños", "content": "🎂 ¡Feliz cumpleaños {{nombre}}! {{business_name}} te desea un día increíble y tiene un regalo especial para ti. Pregunta por tu descuento de cumpleaños."},
    {"name": "Encuesta rápida", "category": "Encuesta", "content": "{{nombre}}, ayúdanos a mejorar. ¿Cómo calificas tu experiencia con {{business_name}}? Responde 1 (Malo) a 5 (Excelente)."},
    {"name": "Descuento por recomendación", "category": "Descuento", "content": "{{nombre}}, recomienda {{business_name}} a un amigo y ambos reciben un descuento. Pide tu código de referido."},
    {"name": "Invitación evento", "category": "Evento", "content": "{{nombre}}, te invitamos al próximo evento de {{business_name}}. Cupo limitado. Confirma tu asistencia."},
    {"name": "Carrito abandonado", "category": "Recordatorio", "content": "{{nombre}}, dejaste productos en tu carrito. En {{business_name}} queremos ayudarte a completar tu compra. ¿Te interesa?"},
]


class SeedTemplateOut(BaseModel):
    name: str
    category: str | None
    content: str


@router.get("/seeds", response_model=list[SeedTemplateOut])
async def list_seed_templates():
    return [SeedTemplateOut(**t) for t in SEED_TEMPLATES]


@router.post("/seed-all", status_code=status.HTTP_201_CREATED)
async def seed_all_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = await db.execute(
        select(MessageTemplate).where(MessageTemplate.advertiser_id == current_user.id)
    )
    existing_names = {t.name for t in existing.scalars().all()}

    created = 0
    for t in SEED_TEMPLATES:
        if t["name"] not in existing_names:
            template = MessageTemplate(
                advertiser_id=current_user.id,
                name=t["name"],
                content=t["content"],
                category=t["category"],
            )
            db.add(template)
            created += 1

    await db.commit()
    return {"message": f"{created} plantillas importadas", "created": created}
