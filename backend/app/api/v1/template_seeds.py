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
    # ─── Campaña ────────────────────────────────────────────
    {"name": "Bienvenida", "category": "Bienvenida", "step": None, "content": "¡Hola {{nombre}}! Gracias por contactar a {{negocio}}. Estamos aquí para ayudarte. ¿En qué podemos servirte hoy?"},
    {"name": "Promoción general", "category": "Promoción", "step": None, "content": "¡Hola {{nombre}}! {{negocio}} tiene una oferta especial para ti. Válida hasta agotar existencias. ¡Aprovecha!"},
    {"name": "Recordatorio de cita", "category": "Recordatorio", "step": None, "content": "Recordatorio {{nombre}}: Tienes una cita con {{negocio}} mañana. Confirma tu asistencia respondiendo este mensaje."},
    {"name": "Seguimiento post-venta", "category": "Seguimiento", "step": None, "content": "Hola {{nombre}}, ¿cómo te fue con tu compra en {{negocio}}? Nos importa tu opinión. ¡Gracias por preferirnos!"},
    {"name": "Oferta por tiempo limitado", "category": "Oferta", "step": None, "content": "Oferta exclusiva {{nombre}}! {{negocio}} te ofrece un descuento especial solo por hoy. Pide más información."},
    {"name": "Cumpleaños", "category": "Cumpleaños", "step": None, "content": "¡Feliz cumpleaños {{nombre}}! {{negocio}} te desea un día increíble y tiene un regalo especial para ti. Pregunta por tu descuento de cumpleaños."},
    {"name": "Encuesta rápida", "category": "Encuesta", "step": None, "content": "{{nombre}}, ayúdanos a mejorar. ¿Cómo calificas tu experiencia con {{negocio}}? Responde 1 (Malo) a 5 (Excelente)."},
    {"name": "Descuento por recomendación", "category": "Descuento", "step": None, "content": "{{nombre}}, recomienda {{negocio}} a un amigo y ambos reciben un descuento. Pide tu código de referido."},
    {"name": "Invitación evento", "category": "Evento", "step": None, "content": "{{nombre}}, te invitamos al próximo evento de {{negocio}}. Cupo limitado. Confirma tu asistencia."},
    {"name": "Carrito abandonado", "category": "Recordatorio", "step": None, "content": "{{nombre}}, dejaste productos en tu carrito. En {{negocio}} queremos ayudarte a completar tu compra. ¿Te interesa?"},

    # ─── Pedido ─────────────────────────────────────────────
    {"name": "Confirmar pedido", "category": "Pedido", "step": "order_confirm", "content": "¡Gracias por tu interés! ¿Te gustaría hacer un pedido? Responde *Sí* o *No*"},
    {"name": "Pedir nombre", "category": "Pedido", "step": "order_name", "content": "¡Excelente! Para completarlo, ¿a qué nombre va el pedido?"},
    {"name": "Pedir dirección", "category": "Pedido", "step": "order_address", "content": "Perfecto, {{primer_nombre}}. ¿Cuál es tu dirección de entrega?"},
    {"name": "Pedir forma de pago", "category": "Pedido", "step": "order_payment", "content": "¡Anotado! ¿Cómo prefieres pagar? Responde: *Efectivo*, *Tarjeta* o *Transferencia*"},
    {"name": "Pedido confirmado", "category": "Pedido", "step": "order_confirmed", "content": "✅ *Pedido #{{order_number}} confirmado*\n\n🛒 {{items}}\n👤 {{nombre}}\n📍 {{direccion}}\n💳 {{pago}}\n\n¡Gracias! En breve te contactamos para confirmar el tiempo de entrega."},
    {"name": "Notificar dueño pedido", "category": "Pedido", "step": "order_owner_notify", "content": "📦 *NUEVO PEDIDO #{{order_number}}*\n────────────────\n🛒 {{items}}\n👤 Cliente: {{nombre}}\n📱 WhatsApp: {{telefono}}\n📍 Dirección: {{direccion}}\n💳 Pago: {{pago}}\n────────────────\nResponde a este número para contactar al cliente."},

    # ─── Plan ───────────────────────────────────────────────
    {"name": "Confirmar plan", "category": "Plan", "step": "plan_confirm", "content": "¡Excelente elección! ¿Confirmas que quieres el *Plan {{plan}}*? Responde *Sí* o *No*"},
    {"name": "Nombre para plan", "category": "Plan", "step": "plan_name", "content": "¡Excelente! ¿A qué nombre te registramos?"},
    {"name": "Fecha activación plan", "category": "Plan", "step": "plan_datetime", "content": "Perfecto, {{primer_nombre}}. ¿Qué día y hora prefieres para tu cita de activación?\nPor ejemplo: *Mañana a las 10 am* o *Viernes a las 4 pm*"},
    {"name": "Plan confirmado", "category": "Plan", "step": "plan_confirmed", "content": "✅ *Plan {{plan}} registrado*\n\n👤 {{nombre}}\n📅 Preferencia: {{fecha}}\n\nTe contactaremos pronto para confirmar los detalles y activar tu plan. ¡Gracias!"},

    # ─── Cita ───────────────────────────────────────────────
    {"name": "Confirmar cita", "category": "Cita", "step": "appt_confirm", "content": "✅ *¡Cita confirmada!*\n\n📌 {{servicio}}\n🕐 {{fecha}} a las {{hora}}\n🏪 {{negocio}}\n\n¡Te esperamos! Si necesitas reagendar escríbenos."},
    {"name": "Cancelar cita", "category": "Cita", "step": "appt_cancel", "content": "❌ Cita cancelada.\n\nSin problema, {{primer_nombre}}.\n¿Te gustaría que te muestre los horarios disponibles para reagendar tu cita? Responde *SÍ* o *NO*"},
    {"name": "Reagendar cita (sí)", "category": "Cita", "step": "appt_reschedule_yes", "content": "¡Genial! Por favor escríbeme qué día y hora prefieres esta semana y revisaré la disponibilidad para agendarte."},
    {"name": "Reagendar cita (no)", "category": "Cita", "step": "appt_reschedule_no", "content": "Entendido. ¡Escríbenos cuando estés listo/a!"},
    {"name": "Recordatorio cita 24h", "category": "Cita", "step": "appt_reminder_24h", "content": "Recordatorio {{nombre}}: Mañana tienes una cita con {{negocio}}.\n\n📌 {{servicio}}\n🕐 {{fecha}} a las {{hora}}\n\nResponde *1* para confirmar o *2* para cancelar."},
]


class SeedTemplateOut(BaseModel):
    name: str
    category: str | None
    step: str | None = None
    content: str


@router.get("/seeds", response_model=list[SeedTemplateOut])
async def list_seed_templates() -> list[SeedTemplateOut]:
    return [SeedTemplateOut(**t) for t in SEED_TEMPLATES]


@router.post("/seed-all", status_code=status.HTTP_201_CREATED)
async def seed_all_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
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
                step=t.get("step"),
            )
            db.add(template)
            created += 1

    await db.commit()
    return {"message": f"{created} plantillas importadas", "created": created}
