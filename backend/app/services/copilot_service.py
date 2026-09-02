"""
Copiloto CRM — orquestador de tool-calling con Claude para que el anunciante
autenticado opere su propio CRM (contactos, campañas, cupones, citas) en
lenguaje natural desde el dashboard.

100% interno: nunca toca WhatsApp/Meta, es un chat web sobre la propia API
REST de la app. Llama a anthropic.AsyncAnthropic directamente (no
llm_client.chat_completion — ese helper es texto plano, sin tool use).

Confirmación de acciones costosas/irreversibles (launch_campaign,
create_coupon, schedule_appointment): en vez de un dict en memoria (Railway
corre múltiples workers — un dict local no sobrevive a que /confirm caiga en
otro proceso), el tool call pendiente se codifica en un JWT firmado con
python-jose + settings.SECRET_KEY (el mismo primitivo que ya usa
app/core/security.py para access/refresh tokens) con expiración corta. Ese
token ES el confirmation_id — decodificarlo y verificar firma/expiración/
dueño es toda la validación que necesita /confirm, sin estado compartido.
"""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import anthropic
from jose import jwt
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import decode_token
from app.models.appointment import Appointment
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.user import User
from app.schemas.contact import ContactCreate
from app.services.analytics_service import capture_event
from app.services.availability_service import TZ
from app.services.campaign_stats_service import compute_campaign_stats, merge_stats
from app.services.coupon_service import default_expiry, generate_coupon_code
from app.services.send_block_explain import preflight_campaign_send

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5
CONFIRMATION_TTL_MINUTES = 5
_MAX_TARGET_CONTACTS = 2000

CONFIRM_TOOLS = {"launch_campaign", "create_coupon", "schedule_appointment"}


# ─── Cliente Anthropic ────────────────────────────────────────────────────────

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


# ─── System prompt ────────────────────────────────────────────────────────────

def _build_system_prompt(user: User) -> str:
    business = user.business_name or "tu negocio"
    return f"""Eres el Copiloto CRM de AdRadio, el asistente interno del panel de {business}.
Ayudas al dueño del negocio a operar SU PROPIO CRM (contactos, campañas, cupones y citas)
en lenguaje natural, usando ÚNICAMENTE las herramientas que tienes disponibles.

Reglas estrictas:
1. Habla siempre en español, con tono claro, profesional y directo. Sé breve.
2. NUNCA inventes datos: nombres, cifras, estados de campañas o citas deben salir
   siempre de un resultado real de una herramienta. Si no tienes el dato, dilo y
   ofrece consultarlo — no lo adivines ni lo aproximes.
3. Este chat es 100% interno del panel — NO envías mensajes de WhatsApp, no conectas
   Meta, no hablas con los clientes finales del negocio. Solo operas los datos del CRM
   a través de tus herramientas.
4. Si te piden algo fuera de tus herramientas (mandar un WhatsApp directo, conectar
   Meta, cambiar el plan de suscripción, etc.), dilo con claridad y NO inventes que
   lo hiciste ni finjas que ocurrió.
5. Crear cupones, lanzar campañas o agendar citas son acciones costosas o difíciles
   de revertir — el sistema SIEMPRE le pedirá confirmación explícita al usuario antes
   de ejecutarlas, con una tarjeta separada que el usuario debe aprobar. Por eso, en
   cuanto tengas los datos que la herramienta necesita (usa list_contacts/list_campaigns
   primero si te falta un id), LLAMA la herramienta directamente en ese mismo turno —
   no le preguntes al usuario en tus propias palabras si confirma ni le pidas permiso
   en texto plano antes de llamarla, eso solo duplica la confirmación que el sistema
   ya va a pedir. Nunca asumas que ya fue confirmada ni la des por hecha en tu respuesta.
6. Listar contactos/campañas y consultar estadísticas son de lectura — ejecútalas
   directamente cuando te ayuden a responder. Crear un contacto es barato y reversible
   — también se ejecuta directo.
"""


# ─── Definición de herramientas (Anthropic tool-use schema) ──────────────────

TOOLS = [
    {
        "name": "list_contacts",
        "description": (
            "Busca y lista contactos del CRM del anunciante autenticado. Úsalo para "
            "responder preguntas como '¿cuántos contactos tengo?', 'muéstrame los "
            "contactos con la etiqueta X', o 'busca a Juan'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Texto libre para buscar por nombre o teléfono."},
                "tag": {"type": "string", "description": "Filtra por una etiqueta exacta del contacto."},
                "limit": {"type": "integer", "description": "Máximo de resultados a devolver (default 10).", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "list_campaigns",
        "description": "Lista las campañas del anunciante, opcionalmente filtradas por estado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filtra por estado de la campaña.",
                    "enum": ["draft", "scheduled", "running", "paused", "completed"],
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_campaign_stats",
        "description": (
            "Obtiene las estadísticas reales (enviados, entregados, leídos, fallidos, "
            "cupones canjeados) de una campaña específica, por id o por nombre."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id_or_name": {
                    "type": "string",
                    "description": "El id (UUID) o el nombre (o parte del nombre) de la campaña.",
                },
            },
            "required": ["campaign_id_or_name"],
        },
    },
    {
        "name": "create_contact",
        "description": (
            "Crea un nuevo contacto en el CRM. Acción barata y reversible — se ejecuta "
            "de inmediato, sin pedir confirmación."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre del contacto."},
                "phone": {"type": "string", "description": "Teléfono en formato E.164, ej. +5215512345678."},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Etiquetas opcionales para el contacto.",
                },
            },
            "required": ["name", "phone"],
        },
    },
    {
        "name": "launch_campaign",
        "description": (
            "Lanza (envía) una campaña existente a sus contactos objetivo. Acción "
            "costosa e irreversible una vez enviada — SIEMPRE requiere confirmación "
            "explícita del usuario antes de ejecutarse."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": (
                        "El id (UUID) de la campaña a lanzar. Si solo tienes el nombre, "
                        "usa list_campaigns primero para obtener el id."
                    ),
                },
            },
            "required": ["campaign_id"],
        },
    },
    {
        "name": "create_coupon",
        "description": (
            "Crea uno o varios cupones de descuento para contactos del CRM. Acción "
            "costosa y difícil de revertir — SIEMPRE requiere confirmación explícita "
            "del usuario antes de ejecutarse."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre o descripción corta del cupón."},
                "discount_percent": {
                    "type": "number",
                    "description": "Porcentaje de descuento, entre 1 y 100.",
                },
                "target": {
                    "type": "string",
                    "enum": ["all", "segment", "contact"],
                    "description": (
                        "A quién va dirigido: 'all' (todos los contactos activos), "
                        "'segment' (contactos con una etiqueta) o 'contact' (un solo contacto)."
                    ),
                },
                "contact_id": {
                    "type": "string",
                    "description": (
                        "Requerido si target es 'contact'. El id (UUID) del contacto — "
                        "usa list_contacts primero si no lo tienes."
                    ),
                },
                "segment_tag": {
                    "type": "string",
                    "description": "Requerido si target es 'segment'. La etiqueta que deben tener los contactos.",
                },
            },
            "required": ["name", "discount_percent", "target"],
        },
    },
    {
        "name": "schedule_appointment",
        "description": (
            "Agenda una cita para un contacto existente. Acción difícil de revertir — "
            "SIEMPRE requiere confirmación explícita del usuario antes de ejecutarse."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_id": {
                    "type": "string",
                    "description": "El id (UUID) del contacto — usa list_contacts primero si no lo tienes.",
                },
                "datetime_iso": {
                    "type": "string",
                    "description": "Fecha y hora de la cita en formato ISO 8601, ej. 2026-09-10T15:00:00.",
                },
                "service": {"type": "string", "description": "Servicio o motivo de la cita."},
            },
            "required": ["contact_id", "datetime_iso"],
        },
    },
]


# ─── Confirmación firmada (stateless) ─────────────────────────────────────────

def _create_confirmation_token(user_id, tool: str, args: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=CONFIRMATION_TTL_MINUTES)
    payload = {
        "sub": str(user_id),
        "type": "copilot_confirm",
        "tool": tool,
        "args": args,
        "jti": uuid.uuid4().hex,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def _claim_confirmation_once(redis, jti: str) -> bool:
    """Marca un jti de confirmación como usado en Redis (compartido entre
    workers, a diferencia del token en sí que solo prueba autenticidad).
    Sin esto, el mismo confirmation_id sigue siendo válido hasta que expira
    — un doble clic, un retry de red, o dos /confirm concurrentes podrían
    lanzar la campaña dos veces, duplicar cupones, o duplicar la cita. Si
    Redis no está disponible, degrada a "sin protección extra" (mismo riesgo
    que antes) en vez de bloquear la acción."""
    if redis is None:
        return True
    try:
        claimed = await redis.set(
            f"copilot_confirm_used:{jti}", "1", nx=True, ex=CONFIRMATION_TTL_MINUTES * 60
        )
        return bool(claimed)
    except Exception:
        logger.warning("[COPILOT] Redis claim check failed, proceeding without it", exc_info=True)
        return True


def _decode_confirmation_token(token: str) -> dict | None:
    payload = decode_token(token)
    if not payload or payload.get("type") != "copilot_confirm":
        return None
    return payload


# ─── Helpers de formato ────────────────────────────────────────────────────────

def _tool_result_block(tool_use_id: str, data: dict, is_error: bool = False) -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(data, default=str, ensure_ascii=False),
        "is_error": is_error,
    }


def _default_confirmation_reply(summary: str) -> str:
    return f"Antes de hacerlo, confirmemos: {summary}"


def _summarize(tool_name: str, data: dict) -> str:
    if data.get("error"):
        return f"No se pudo completar la acción: {data['error']}"
    if tool_name == "list_contacts":
        return f"Se encontraron {data.get('count', 0)} contacto(s)."
    if tool_name == "list_campaigns":
        return f"Se encontraron {data.get('count', 0)} campaña(s)."
    if tool_name == "get_campaign_stats":
        return f"Estadísticas de la campaña \"{data.get('name', '')}\"."
    if tool_name == "create_contact":
        return f"Contacto \"{data.get('name', '')}\" creado."
    if tool_name == "launch_campaign":
        return f"Campaña \"{data.get('name', '')}\" lanzada a {data.get('recipients', 0)} contacto(s)."
    if tool_name == "create_coupon":
        return f"Se creó {data.get('count', 0)} cupón(es) de {data.get('discount_percent')}% de descuento."
    if tool_name == "schedule_appointment":
        return f"Cita agendada para {data.get('customer_name', '')} el {data.get('scheduled_at', '')}."
    return tool_name


# ─── Herramientas de lectura / escritura barata (ejecución inmediata) ─────────

async def _tool_list_contacts(db: AsyncSession, user: User, args: dict) -> dict:
    query = (args.get("query") or "").strip()
    tag = (args.get("tag") or "").strip()
    try:
        limit = min(max(int(args.get("limit") or 10), 1), 50)
    except (TypeError, ValueError):
        limit = 10

    q = select(Contact).where(Contact.advertiser_id == user.id)
    if tag:
        q = q.where(Contact.tags.any(tag))
    if query:
        like = f"%{query}%"
        q = q.where(or_(Contact.name.ilike(like), Contact.phone.ilike(like)))
    q = q.order_by(Contact.created_at.desc()).limit(limit)

    rows = (await db.execute(q)).scalars().all()
    items = [
        {
            "id": str(c.id),
            "name": c.name,
            "phone": c.phone,
            "tags": c.tags or [],
            "status": c.status,
            "pipeline_stage": c.pipeline_stage,
        }
        for c in rows
    ]
    return {"count": len(items), "items": items}


async def _tool_list_campaigns(db: AsyncSession, user: User, args: dict) -> dict:
    status_filter = (args.get("status") or "").strip()
    q = select(Campaign).where(Campaign.advertiser_id == user.id)
    if status_filter:
        q = q.where(Campaign.status == status_filter)
    q = q.order_by(Campaign.created_at.desc()).limit(20)

    rows = (await db.execute(q)).scalars().all()
    items = [{"id": str(c.id), "name": c.name, "type": c.type, "status": c.status} for c in rows]
    return {"count": len(items), "items": items}


async def _find_campaign(db: AsyncSession, user: User, ident: str) -> Campaign | None:
    ident = (ident or "").strip()
    if not ident:
        return None
    try:
        cid = uuid.UUID(ident)
    except ValueError:
        cid = None
    if cid:
        result = await db.execute(
            select(Campaign).where(Campaign.id == cid, Campaign.advertiser_id == user.id)
        )
        campaign = result.scalar_one_or_none()
        if campaign:
            return campaign

    like = f"%{ident}%"
    result = await db.execute(
        select(Campaign)
        .where(Campaign.advertiser_id == user.id, Campaign.name.ilike(like))
        .order_by(Campaign.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _tool_get_campaign_stats(db: AsyncSession, user: User, args: dict) -> dict:
    ident = args.get("campaign_id_or_name") or ""
    campaign = await _find_campaign(db, user, ident)
    if not campaign:
        return {"error": f"No encontré ninguna campaña que coincida con \"{ident}\"."}

    derived = await compute_campaign_stats(db, [campaign.id])
    stats = merge_stats(campaign.stats, derived.get(campaign.id))
    return {
        "id": str(campaign.id),
        "name": campaign.name,
        "type": campaign.type,
        "status": campaign.status,
        "stats": stats,
    }


async def _tool_create_contact(db: AsyncSession, user: User, args: dict) -> dict:
    try:
        body = ContactCreate(
            name=(args.get("name") or "").strip(),
            phone=(args.get("phone") or "").strip(),
            tags=args.get("tags") or [],
        )
    except ValidationError as e:
        return {"error": "; ".join(err["msg"] for err in e.errors())}

    existing = await db.execute(
        select(Contact).where(Contact.advertiser_id == user.id, Contact.phone == body.phone)
    )
    if existing.scalar_one_or_none():
        return {"error": "Ya existe un contacto con ese número"}

    contact = Contact(advertiser_id=user.id, **body.model_dump())
    db.add(contact)
    await db.commit()
    await db.refresh(contact)

    logger.info("[COPILOT] Contact created: %s (%s) by user %s", contact.name, contact.phone, user.id)
    capture_event("contact_created", user_id=user.id, properties={"source": "copilot"})

    try:
        from app.services.webhook_dispatcher import dispatch_webhook_event

        await dispatch_webhook_event(
            "contact.created",
            {"id": str(contact.id), "name": contact.name, "phone": contact.phone},
            db,
            advertiser_id=user.id,
        )
    except Exception:
        logger.warning("[COPILOT] webhook dispatch for contact.created failed", exc_info=True)

    return {"id": str(contact.id), "name": contact.name, "phone": contact.phone, "tags": contact.tags or []}


async def _execute_immediate_tool(db: AsyncSession, user: User, tool_name: str, args: dict) -> dict:
    try:
        if tool_name == "list_contacts":
            return await _tool_list_contacts(db, user, args)
        if tool_name == "list_campaigns":
            return await _tool_list_campaigns(db, user, args)
        if tool_name == "get_campaign_stats":
            return await _tool_get_campaign_stats(db, user, args)
        if tool_name == "create_contact":
            return await _tool_create_contact(db, user, args)
        return {"error": f"Herramienta desconocida: {tool_name}"}
    except Exception as e:
        logger.warning("[COPILOT] Tool %s failed: %s", tool_name, e, exc_info=True)
        return {"error": "Ocurrió un error al ejecutar esta acción."}


# ─── Herramientas costosas: preview (confirmación) + ejecución ───────────────

async def _count_campaign_recipients(db: AsyncSession, campaign: Campaign) -> int:
    """Misma resolución de segmento que tasks.py's schedule_campaign — contactos
    activos del anunciante, filtrados por specific_contacts o tags si el
    segmento los especifica."""
    segment = campaign.segment or {}
    specific = segment.get("specific_contacts") or []
    tags = segment.get("tags") or []

    q = select(func.count()).select_from(Contact).where(
        Contact.advertiser_id == campaign.advertiser_id, Contact.status == "active"
    )
    if specific:
        try:
            ids = [uuid.UUID(c) for c in specific]
        except ValueError:
            ids = []
        q = q.where(Contact.id.in_(ids))
    elif tags:
        q = q.where(Contact.tags.overlap(tags))

    result = await db.execute(q)
    return result.scalar_one()


async def _preview_launch_campaign(db: AsyncSession, user: User, args: dict) -> tuple[str | None, dict | None, str | None]:
    ident = str(args.get("campaign_id") or "").strip()
    if not ident:
        return None, None, "Falta el id de la campaña."

    campaign = await _find_campaign(db, user, ident)
    if not campaign:
        return None, None, f"No encontré ninguna campaña que coincida con \"{ident}\"."

    if campaign.status not in ("draft", "scheduled", "paused"):
        return None, None, (
            f"La campaña \"{campaign.name}\" no se puede lanzar porque su estado actual "
            f"es \"{campaign.status}\"."
        )

    ab = campaign.ab_test or {}
    mode = ab.get("campaign_mode", "regular")
    if campaign.status == "draft":
        if mode in ("radio", "comunitaria") and not ab.get("audio_url"):
            return None, None, f"La campaña \"{campaign.name}\" aún no tiene el audio generado — complétalo en el dashboard antes de lanzarla."
        if mode == "banner" and not campaign.image_url:
            return None, None, f"La campaña \"{campaign.name}\" aún no tiene el banner generado — complétalo en el dashboard antes de lanzarla."
        if not campaign.message_text and mode == "regular":
            return None, None, f"La campaña \"{campaign.name}\" no tiene mensaje — agrégalo antes de lanzarla."

    recipients = await _count_campaign_recipients(db, campaign)
    if recipients == 0:
        return None, None, f"La campaña \"{campaign.name}\" no tiene contactos activos en su segmento — no hay a quién enviarla."

    blocked = await preflight_campaign_send(db, campaign, user)
    if blocked:
        return None, None, blocked

    summary = (
        f"Vas a lanzar la campaña \"{campaign.name}\" a {recipients} contacto(s). "
        f"Tu cuenta tiene {user.messages_remaining} mensajes disponibles en tu plan. "
        "Esta acción no se puede deshacer una vez enviada."
    )
    resolved_args = {"campaign_id": str(campaign.id)}
    return summary, resolved_args, None


async def _execute_launch_campaign(db: AsyncSession, user: User, args: dict) -> tuple[dict | None, str | None]:
    try:
        cid = uuid.UUID(str(args.get("campaign_id")))
    except (ValueError, TypeError):
        return None, "El id de la campaña no es válido."

    result = await db.execute(
        select(Campaign).where(Campaign.id == cid, Campaign.advertiser_id == user.id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        return None, "Esa campaña ya no existe."
    if campaign.status not in ("draft", "scheduled", "paused"):
        return None, f"La campaña \"{campaign.name}\" ya no está en un estado que se pueda lanzar (estado actual: {campaign.status})."

    blocked = await preflight_campaign_send(db, campaign, user)
    if blocked:
        return None, blocked

    recipients = await _count_campaign_recipients(db, campaign)

    campaign.status = "running"
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error("[COPILOT] Error lanzando campaña %s: %s", cid, e, exc_info=True)
        return None, "Ocurrió un error al lanzar la campaña. Intenta de nuevo."

    from app.workers.tasks import schedule_campaign

    schedule_campaign.delay(str(campaign.id))
    capture_event(
        "campaign_sent",
        user_id=user.id,
        properties={"campaign_id": str(campaign.id), "type": campaign.type, "source": "copilot"},
    )

    return {
        "campaign_id": str(campaign.id),
        "name": campaign.name,
        "status": "running",
        "recipients": recipients,
    }, None


async def _resolve_coupon_targets(
    db: AsyncSession, user: User, target: str, contact_id: str | None, segment_tag: str | None,
) -> tuple[list[Contact] | None, str | None]:
    if target == "contact":
        if not contact_id:
            return None, "Falta el contact_id para un cupón individual."
        try:
            cid = uuid.UUID(str(contact_id))
        except ValueError:
            return None, "El contact_id no es válido."
        result = await db.execute(
            select(Contact).where(Contact.id == cid, Contact.advertiser_id == user.id)
        )
        contact = result.scalar_one_or_none()
        if not contact:
            return None, "No encontré ese contacto."
        return [contact], None

    if target == "segment":
        if not segment_tag:
            return None, "Falta la etiqueta (segment_tag) para el cupón por segmento."
        result = await db.execute(
            select(Contact)
            .where(
                Contact.advertiser_id == user.id,
                Contact.status == "active",
                Contact.tags.any(segment_tag),
            )
            .limit(_MAX_TARGET_CONTACTS)
        )
        return result.scalars().all(), None

    if target == "all":
        result = await db.execute(
            select(Contact)
            .where(Contact.advertiser_id == user.id, Contact.status == "active")
            .limit(_MAX_TARGET_CONTACTS)
        )
        return result.scalars().all(), None

    return None, "El destino del cupón debe ser 'all', 'segment' o 'contact'."


def _target_description(target: str, contacts: list[Contact]) -> str:
    if target == "contact":
        c = contacts[0]
        return f"{c.name} ({c.phone})"
    if target == "segment":
        return f"{len(contacts)} contacto(s) con esa etiqueta"
    return f"todos tus {len(contacts)} contacto(s) activos"


async def _preview_create_coupon(db: AsyncSession, user: User, args: dict) -> tuple[str | None, dict | None, str | None]:
    name = (args.get("name") or "").strip()
    if not name:
        return None, None, "Falta el nombre del cupón."

    try:
        discount = float(args.get("discount_percent"))
    except (TypeError, ValueError):
        return None, None, "El porcentaje de descuento no es válido."
    if not (0 < discount <= 100):
        return None, None, "El porcentaje de descuento debe estar entre 1 y 100."

    target = args.get("target")
    contacts, error = await _resolve_coupon_targets(db, user, target, args.get("contact_id"), args.get("segment_tag"))
    if error:
        return None, None, error
    if not contacts:
        return None, None, "No encontré contactos que coincidan con ese destino."

    summary = (
        f"Vas a crear {len(contacts)} cupón(es) de {discount}% de descuento (\"{name}\") "
        f"para {_target_description(target, contacts)}, válido(s) por 72 horas desde que "
        "confirmes. Esta acción no se puede deshacer."
    )
    resolved_args = {
        "name": name,
        "discount_percent": discount,
        "target": target,
        "contact_ids": [str(c.id) for c in contacts],
    }
    return summary, resolved_args, None


async def _execute_create_coupon(db: AsyncSession, user: User, args: dict) -> tuple[dict | None, str | None]:
    contact_ids = args.get("contact_ids") or []
    try:
        ids = [uuid.UUID(cid) for cid in contact_ids]
    except ValueError:
        return None, "Los identificadores de contacto no son válidos."

    result = await db.execute(
        select(Contact).where(Contact.id.in_(ids), Contact.advertiser_id == user.id)
    )
    contacts = result.scalars().all()
    if not contacts:
        return None, "Los contactos de este cupón ya no existen."

    name = args.get("name") or "Cupón"
    discount_percent = args.get("discount_percent")
    expires = default_expiry()
    coupons: list[Coupon] = []
    for c in contacts:
        coupon = Coupon(
            advertiser_id=user.id,
            contact_id=c.id,
            campaign_id=None,
            source="copilot",
            code=generate_coupon_code(),
            description=str(name)[:255],
            discount_type="percentage",
            discount_value=Decimal(str(discount_percent)),
            expires_at=expires,
        )
        db.add(coupon)
        coupons.append(coupon)

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error("[COPILOT] Error creando cupones: %s", e, exc_info=True)
        return None, "Ocurrió un error al crear los cupones. Intenta de nuevo."

    capture_event(
        "coupon_created", user_id=user.id,
        properties={"count": len(coupons), "target": args.get("target"), "source": "copilot"},
    )

    return {
        "count": len(coupons),
        "name": name,
        "discount_percent": discount_percent,
        "target": args.get("target"),
        "expires_at": expires.isoformat(),
        "coupon_codes": [c.code for c in coupons][:20],
    }, None


async def _preview_schedule_appointment(db: AsyncSession, user: User, args: dict) -> tuple[str | None, dict | None, str | None]:
    contact_id = args.get("contact_id")
    dt_iso = args.get("datetime_iso")
    service = (args.get("service") or "Cita").strip()

    if not contact_id or not dt_iso:
        return None, None, "Falta el contacto o la fecha/hora de la cita."

    try:
        cid = uuid.UUID(str(contact_id))
    except ValueError:
        return None, None, "El contact_id no es válido."

    result = await db.execute(
        select(Contact).where(Contact.id == cid, Contact.advertiser_id == user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        return None, None, "No encontré ese contacto."

    try:
        dt = datetime.fromisoformat(str(dt_iso).replace("Z", "+00:00"))
    except ValueError:
        return None, None, "La fecha/hora no tiene un formato válido (usa ISO 8601)."
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)

    if dt < datetime.now(timezone.utc):
        return None, None, "Esa fecha/hora ya pasó — elige una fecha futura."

    summary = (
        f"Vas a agendar una cita (\"{service}\") con {contact.name} ({contact.phone}) "
        f"el {dt.strftime('%d/%m/%Y')} a las {dt.strftime('%H:%M')}."
    )
    resolved_args = {"contact_id": str(contact.id), "datetime_iso": dt.isoformat(), "service": service}
    return summary, resolved_args, None


async def _execute_schedule_appointment(db: AsyncSession, user: User, args: dict) -> tuple[dict | None, str | None]:
    try:
        cid = uuid.UUID(str(args.get("contact_id")))
    except (ValueError, TypeError):
        return None, "El contact_id no es válido."

    result = await db.execute(
        select(Contact).where(Contact.id == cid, Contact.advertiser_id == user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        return None, "Ese contacto ya no existe."

    try:
        dt = datetime.fromisoformat(str(args.get("datetime_iso")))
    except (ValueError, TypeError):
        return None, "La fecha/hora no es válida."

    service = args.get("service") or "Cita"
    appointment = Appointment(
        advertiser_id=user.id,
        contact_id=contact.id,
        customer_name=contact.name,
        customer_phone=contact.phone,
        service=service,
        scheduled_at=dt,
        duration_min=30,
        status="confirmed",
    )
    db.add(appointment)

    if user.google_calendar_connected and user.google_refresh_token:
        try:
            from app.services.calendar_service import create_event

            event_id = create_event(
                refresh_token=user.google_refresh_token,
                summary=f"📅 {service} — {contact.name}",
                description=f"Cliente: {contact.name}\nTeléfono: {contact.phone or ''}",
                start_dt=dt,
                duration_min=30,
                customer_phone=contact.phone,
            )
            appointment.google_event_id = event_id
        except Exception as e:
            logger.warning("[COPILOT] Google Calendar sync failed: %s", e)

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error("[COPILOT] Error agendando cita: %s", e, exc_info=True)
        return None, "Ocurrió un error al agendar la cita. Intenta de nuevo."

    await db.refresh(appointment)
    capture_event("appointment_created", user_id=user.id, properties={"source": "copilot"})

    return {
        "appointment_id": str(appointment.id),
        "customer_name": appointment.customer_name,
        "service": appointment.service,
        "scheduled_at": appointment.scheduled_at.isoformat(),
        "status": appointment.status,
    }, None


async def _preview_confirm_tool(db: AsyncSession, user: User, tool_name: str, args: dict) -> tuple[str | None, dict | None, str | None]:
    try:
        if tool_name == "launch_campaign":
            return await _preview_launch_campaign(db, user, args)
        if tool_name == "create_coupon":
            return await _preview_create_coupon(db, user, args)
        if tool_name == "schedule_appointment":
            return await _preview_schedule_appointment(db, user, args)
        return None, None, "No reconozco esa acción."
    except Exception as e:
        logger.warning("[COPILOT] Preview failed for %s: %s", tool_name, e, exc_info=True)
        return None, None, "Ocurrió un error al preparar esta acción. Intenta de nuevo."


async def _execute_confirm_tool(db: AsyncSession, user: User, tool_name: str, args: dict) -> tuple[dict | None, str | None]:
    try:
        if tool_name == "launch_campaign":
            return await _execute_launch_campaign(db, user, args)
        if tool_name == "create_coupon":
            return await _execute_create_coupon(db, user, args)
        if tool_name == "schedule_appointment":
            return await _execute_schedule_appointment(db, user, args)
        return None, "No reconozco esa acción."
    except Exception as e:
        logger.warning("[COPILOT] Confirm execution failed for %s: %s", tool_name, e, exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        return None, "Ocurrió un error al ejecutar la acción. Intenta de nuevo."


async def _phrase_confirmed_result(user: User, tool_name: str, data: dict) -> str:
    """Una sola llamada a Claude (sin tools) para redactar la confirmación final
    en lenguaje natural a partir del resultado REAL de la acción — mismo
    principio anti-fabricación que el loop principal, solo que aquí no hay
    conversación en curso que continuar (el flujo de /confirm es stateless)."""
    try:
        client = _get_client()
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=300,
            temperature=0.3,
            system=_build_system_prompt(user),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Se acaba de ejecutar la acción '{tool_name}' con este resultado real: "
                        f"{json.dumps(data, default=str, ensure_ascii=False)}. Confírmaselo al "
                        "usuario en una o dos oraciones, en español, sin inventar datos adicionales."
                    ),
                },
            ],
        )
        text = "\n".join(
            b.text for b in response.content if getattr(b, "type", None) == "text"
        ).strip()
        return text or _summarize(tool_name, data)
    except Exception as e:
        logger.warning("[COPILOT] Failed to phrase confirmation result: %s", e, exc_info=True)
        return _summarize(tool_name, data)


# ─── Entradas públicas ─────────────────────────────────────────────────────────

async def handle_chat(db: AsyncSession, user: User, message: str, history: list[dict]) -> dict:
    client = _get_client()
    system = _build_system_prompt(user)

    messages: list[dict] = [
        {"role": h["role"], "content": h["content"]}
        for h in history
        if h.get("role") in ("user", "assistant") and h.get("content")
    ]
    messages.append({"role": "user", "content": message})

    actions: list[dict] = []

    for _ in range(MAX_ITERATIONS):
        try:
            response = await client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=1024,
                temperature=0.2,
                system=system,
                tools=TOOLS,
                messages=messages,
            )
        except Exception as e:
            logger.warning("[COPILOT] Anthropic call failed: %s", e, exc_info=True)
            return {
                "reply": "Tuve un problema para procesar tu mensaje. Intenta de nuevo en un momento.",
                "actions": actions,
                "pending_confirmation": None,
            }

        text_parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        tool_blocks = [b for b in response.content if getattr(b, "type", None) == "tool_use"]

        if not tool_blocks:
            reply = "\n".join(t.strip() for t in text_parts if t and t.strip())
            return {"reply": reply or "Listo.", "actions": actions, "pending_confirmation": None}

        messages.append({"role": "assistant", "content": response.content})
        tool_results: list[dict] = []
        pending: dict | None = None
        pending_reply: str | None = None

        for block in tool_blocks:
            tool_name = block.name
            args = block.input or {}

            if tool_name in CONFIRM_TOOLS:
                summary, resolved_args, error = await _preview_confirm_tool(db, user, tool_name, args)
                if error:
                    tool_results.append(_tool_result_block(block.id, {"error": error}, is_error=True))
                    continue
                confirmation_id = _create_confirmation_token(user.id, tool_name, resolved_args)
                pre_text = "\n".join(t.strip() for t in text_parts if t and t.strip())
                pending_reply = pre_text or _default_confirmation_reply(summary)
                pending = {
                    "confirmation_id": confirmation_id,
                    "tool": tool_name,
                    "summary": summary,
                    "args": resolved_args,
                }
                break
            else:
                data = await _execute_immediate_tool(db, user, tool_name, args)
                actions.append({"tool": tool_name, "summary": _summarize(tool_name, data), "data": data})
                tool_results.append(_tool_result_block(block.id, data, is_error=bool(data.get("error"))))

        if pending:
            return {"reply": pending_reply, "actions": actions, "pending_confirmation": pending}

        messages.append({"role": "user", "content": tool_results})

    return {
        "reply": "No logré terminar esta solicitud — intenta pedírmelo de forma más simple o en pasos.",
        "actions": actions,
        "pending_confirmation": None,
    }


async def handle_confirm(db: AsyncSession, user: User, confirmation_id: str, approve: bool, redis=None) -> dict:
    payload = _decode_confirmation_token(confirmation_id)
    if not payload or payload.get("sub") != str(user.id):
        raise ValueError("Esta confirmación ya expiró, no es válida, o no pertenece a tu cuenta. Pide la acción de nuevo.")

    tool_name = payload.get("tool")
    args = payload.get("args") or {}

    if not approve:
        return {"reply": "Entendido, no hice ningún cambio.", "actions": [], "pending_confirmation": None}

    jti = payload.get("jti")
    if jti and not await _claim_confirmation_once(redis, jti):
        return {
            "reply": "Esta acción ya se procesó — no la repetí para evitar duplicarla.",
            "actions": [],
            "pending_confirmation": None,
        }

    data, error = await _execute_confirm_tool(db, user, tool_name, args)
    if error:
        return {"reply": error, "actions": [], "pending_confirmation": None}

    action = {"tool": tool_name, "summary": _summarize(tool_name, data), "data": data}
    reply = await _phrase_confirmed_result(user, tool_name, data)
    return {"reply": reply, "actions": [action], "pending_confirmation": None}
