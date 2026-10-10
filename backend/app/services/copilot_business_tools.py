"""Herramientas del Copiloto para el día a día del negocio ("Habla con IaRadio",
paso 2): citas, pedidos, catálogo, horario y el premio de la tarjeta de lealtad.

Lectura (citas, pedidos, productos): se ejecutan directo. Cambios (crear o
editar un producto, cambiar el horario): pasan por la misma confirmación
firmada que campañas y cupones (copilot_service.CONFIRM_TOOLS) — nada se
guarda sin el "sí" del dueño.

Cuando cambia un precio o el horario, también se actualiza el texto de
`bot_instructions` si lo menciona (lo escribe "Configurar por voz"): si no,
el bot seguiría diciendo el precio o el horario viejo.
"""
import logging
import re
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.appointment import Appointment
from app.models.knowledge_base import KnowledgeBase
from app.models.order import Order
from app.models.product import Product
from app.models.user import User
from app.services.availability_service import TZ
from app.services.loyalty_service import LOYALTY_DEFAULTS
from app.services.voice_setup import DAY_LABELS, DAYS, _clean_hours, merge_instructions, render_hours

logger = logging.getLogger(__name__)

_HOUR_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_MAX_LIST = 25

# Las fotos que el dueño sube desde "Habla con IaRadio" (POST /copilot/photo)
# quedan en products/{user_id}/; solo esas se aceptan para un producto.
PHOTO_KEY_PREFIX = "products/{user_id}/"

READ_TOOLS = {"list_appointments", "list_orders", "list_products", "get_bot_status", "test_bot", "open_page_builder"}
CHANGE_TOOLS = {"create_product", "update_product", "update_business_hours", "set_loyalty_reward", "update_bot_info",
                "update_page_style"}

TOOLS = [
    {
        "name": "list_appointments",
        "description": (
            "Lista las citas agendadas en un día o rango de días (hora de México). "
            "Úsalo para '¿qué citas tengo hoy?', '¿quién viene mañana?', 'citas de la semana'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Primer día, AAAA-MM-DD. Si falta, hoy."},
                "date_to": {"type": "string", "description": "Último día, AAAA-MM-DD. Si falta, igual a date_from."},
            },
        },
    },
    {
        "name": "list_orders",
        "description": (
            "Lista los pedidos recientes. Úsalo para '¿qué pedidos tengo?', '¿llegaron pedidos hoy?', "
            "'pedidos pendientes'. Estados: confirmed (confirmado), in_progress (el cliente aún lo está "
            "armando por chat), cancelled."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "state": {
                    "type": "string",
                    "enum": ["all", "confirmed", "in_progress", "cancelled"],
                    "description": "Filtro de estado; por defecto all.",
                },
                "days": {"type": "integer", "description": "Cuántos días hacia atrás (1 = hoy). Por defecto 7."},
            },
        },
    },
    {
        "name": "list_products",
        "description": (
            "Lista o busca productos/servicios del catálogo con su precio. Úsalo antes de "
            "update_product si no tienes el id, o para '¿cuánto tengo el corte?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Texto a buscar en el nombre (opcional)."},
                "include_hidden": {"type": "boolean", "description": "Incluir los ocultos. Por defecto false."},
            },
        },
    },
    {
        "name": "get_bot_status",
        "description": (
            "Revisa qué sabe el bot del cliente y qué le falta: instrucciones, productos con precio, "
            "horario, documentos, página publicada, WhatsApp y premio de lealtad. Úsalo para '¿mi bot está "
            "listo?', '¿qué le falta a mi bot?', '¿ya tengo página?'."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "test_bot",
        "description": (
            "Le hace una pregunta al bot del cliente, como si fuera un cliente, y devuelve lo que "
            "contestaría (con su catálogo, horario, instrucciones y documentos reales). Úsalo para "
            "'pruébame mi bot', 'qué contesta si preguntan el precio del corte'. No envía nada a nadie."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Lo que preguntaría el cliente."},
            },
            "required": ["question"],
        },
    },
    {
        "name": "open_page_builder",
        "description": (
            "Abre el armador guiado de la página del negocio (la tarjeta se va armando mientras el dueño "
            "contesta por voz o con botones; al final la publica). Úsalo cuando pida 'construir mi página', "
            "'quiero mi página web', 'haz mi landing'. Si ya tiene página publicada, devuelve su link en "
            "vez de abrir nada, salvo que quiera cambiarla: entonces pasa edit=true y se abre el mismo "
            "armador ya con lo que tiene (solo pregunta lo que falta). No guarda nada por sí sola: el dueño "
            "publica dentro del armador."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "edit": {"type": "boolean", "description": "true = el dueño quiere cambiar o rehacer su página ya publicada."},
            },
        },
    },
    {
        "name": "create_product",
        "description": (
            "Agrega un producto o servicio al catálogo (el bot lo usa para contestar precios). "
            "Si el dueño adjuntó una foto, pasa su photo_url. SIEMPRE requiere confirmación."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre del producto o servicio."},
                "price": {"type": "number", "description": "Precio en pesos (opcional si no lo dijo)."},
                "description": {"type": "string", "description": "Descripción corta (opcional)."},
                "category": {"type": "string", "description": "Categoría (opcional)."},
                "photo_url": {"type": "string", "description": "URL de la foto que adjuntó el dueño (opcional)."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "update_product",
        "description": (
            "Cambia un producto del catálogo: precio, nombre, descripción, foto, u ocultarlo/mostrarlo "
            "(active). Pasa solo lo que cambia. SIEMPRE requiere confirmación."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product": {"type": "string", "description": "Id o nombre del producto (usa list_products si dudas)."},
                "price": {"type": "number"},
                "name": {"type": "string", "description": "Nombre nuevo."},
                "description": {"type": "string"},
                "photo_url": {"type": "string", "description": "URL de la foto que adjuntó el dueño."},
                "active": {"type": "boolean", "description": "false = ocultarlo del catálogo; true = mostrarlo."},
            },
            "required": ["product"],
        },
    },
    {
        "name": "update_business_hours",
        "description": (
            "Cambia el horario de atención (lo usan la agenda de citas y el bot). Pasa SOLO los "
            "días que cambian: {\"sat\": [\"10:00\", \"14:00\"]} o null para cerrado. Días: "
            "mon, tue, wed, thu, fri, sat, sun. SIEMPRE requiere confirmación."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "changes": {
                    "type": "object",
                    "description": "Día → [abre, cierra] en HH:MM 24 h, o null si ese día cierra.",
                },
            },
            "required": ["changes"],
        },
    },
    {
        "name": "set_loyalty_reward",
        "description": (
            "Pone el premio de la tarjeta de lealtad (y la deja encendida): el cliente lo gana al "
            "juntar los sellos. Usa las palabras del dueño, ej. \"Un corte gratis\". Opcional: "
            "cuántos sellos (3 a 20). SIEMPRE requiere confirmación."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reward": {"type": "string", "description": "El premio, en una línea."},
                "stamps_required": {"type": "integer", "description": "Sellos para ganarlo (3 a 20)."},
            },
            "required": ["reward"],
        },
    },
    {
        "name": "update_bot_info",
        "description": (
            "Cambia lo que el bot sabe del negocio, sin tocar lo demás: dirección o ciudad, formas de "
            "pago, preguntas frecuentes, políticas (garantías, devoluciones, envíos a domicilio) y otros "
            "datos. Pasa SOLO lo que cambia. Para precios y horario usa update_product y "
            "update_business_hours. SIEMPRE requiere confirmación."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Calle o referencia nueva."},
                "city": {"type": "string", "description": "Ciudad nueva."},
                "payment_methods": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Lista COMPLETA de formas de pago (reemplaza la anterior).",
                },
                "add_faqs": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"q": {"type": "string"}, "a": {"type": "string"}}},
                    "description": "Preguntas frecuentes nuevas con su respuesta.",
                },
                "remove_faqs": {"type": "array", "items": {"type": "string"}, "description": "Texto de la pregunta a quitar."},
                "add_policies": {"type": "array", "items": {"type": "string"}, "description": "Políticas nuevas, una por línea."},
                "add_notes": {"type": "array", "items": {"type": "string"}, "description": "Otros datos que el bot debe saber."},
            },
        },
    },
    {
        "name": "update_page_style",
        "description": (
            "Cambia el color de la página del negocio (botones, acentos, su chat) y/o el tema de fondo. "
            "Color: en palabras del dueño (verde, azul, morado, rojo, naranja, rosa, amarillo, turquesa, "
            "café) o en hex #RRGGBB. Tema de fondo: medianoche, pizarra, esmeralda (oscuros), claro o crema. "
            "Pasa solo lo que cambia. SIEMPRE requiere confirmación."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "color": {"type": "string", "description": "Color de acento: nombre en español o #RRGGBB."},
                "theme": {"type": "string", "description": "medianoche, pizarra, esmeralda, claro o crema."},
            },
        },
    },
]


# ─── Utilidades ───────────────────────────────────────────────────────────────

def _local(dt: datetime) -> datetime:
    return dt.astimezone(TZ)


def _parse_day(value, default: date) -> date:
    try:
        return date.fromisoformat(str(value)[:10]) if value else default
    except ValueError:
        return default


def _price(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        d = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    if d < 0 or d > Decimal(10_000_000):
        return None
    return d.quantize(Decimal("0.01"))


def _money(p: Decimal | float | None) -> str:
    if p is None:
        return "sin precio"
    p = float(p)
    return f"${p:,.0f}" if p.is_integer() else f"${p:,.2f}"


def _clean_text(value, limit: int) -> str | None:
    text = " ".join(str(value).split()) if value is not None else ""
    return text[:limit] or None


def _own_photo(user: User, url) -> str | None:
    """Solo fotos que este dueño subió (evita guardar cualquier URL)."""
    if not url:
        return None
    url = str(url)
    return url if PHOTO_KEY_PREFIX.format(user_id=user.id) in url else None


async def _find_product(db: AsyncSession, user: User, ident: str) -> Product | None:
    ident = (ident or "").strip()
    if not ident:
        return None
    try:
        pid = uuid.UUID(ident)
    except ValueError:
        pid = None
    if pid:
        row = (await db.execute(
            select(Product).where(Product.id == pid, Product.advertiser_id == user.id)
        )).scalar_one_or_none()
        if row:
            return row
    rows = (await db.execute(
        select(Product).where(Product.advertiser_id == user.id, Product.name.ilike(f"%{ident}%"))
        .order_by(Product.active.desc(), Product.name).limit(2)
    )).scalars().all()
    # Si el nombre coincide con dos, mejor preguntar que cambiar el que no es.
    exact = [p for p in rows if p.name.strip().lower() == ident.lower()]
    if exact:
        return exact[0]
    return rows[0] if len(rows) == 1 else None


# ─── Lectura ──────────────────────────────────────────────────────────────────

async def list_appointments(db: AsyncSession, user: User, args: dict) -> dict:
    today = datetime.now(TZ).date()
    start = _parse_day(args.get("date_from"), today)
    end = _parse_day(args.get("date_to"), start)
    if end < start:
        start, end = end, start
    end = min(end, start + timedelta(days=31))
    since = datetime.combine(start, time.min, tzinfo=TZ)
    until = datetime.combine(end + timedelta(days=1), time.min, tzinfo=TZ)
    rows = (await db.execute(
        select(Appointment)
        .where(
            Appointment.advertiser_id == user.id,
            Appointment.scheduled_at >= since,
            Appointment.scheduled_at < until,
            Appointment.status != "cancelled",
        )
        .order_by(Appointment.scheduled_at)
        .limit(_MAX_LIST)
    )).scalars().all()
    items = [
        {
            "day": _local(a.scheduled_at).strftime("%Y-%m-%d"),
            "time": _local(a.scheduled_at).strftime("%H:%M"),
            "customer": a.customer_name,
            "service": a.service,
            "status": a.status,
        }
        for a in rows
    ]
    return {"date_from": start.isoformat(), "date_to": end.isoformat(), "count": len(items), "items": items}


_IN_PROGRESS = ("collecting_name", "collecting_address", "collecting_payment")


async def list_orders(db: AsyncSession, user: User, args: dict) -> dict:
    try:
        days = min(max(int(args.get("days") or 7), 1), 90)
    except (TypeError, ValueError):
        days = 7
    since = datetime.combine(datetime.now(TZ).date() - timedelta(days=days - 1), time.min, tzinfo=TZ)
    q = select(Order).where(Order.advertiser_id == user.id, Order.created_at >= since)
    state = args.get("state") or "all"
    if state == "confirmed":
        q = q.where(Order.state == "confirmed")
    elif state == "cancelled":
        q = q.where(Order.state == "cancelled")
    elif state == "in_progress":
        q = q.where(Order.state.in_(_IN_PROGRESS))
    rows = (await db.execute(q.order_by(Order.created_at.desc()).limit(_MAX_LIST))).scalars().all()
    items = [
        {
            "number": o.order_number,
            "when": _local(o.created_at).strftime("%Y-%m-%d %H:%M"),
            "state": "in_progress" if o.state in _IN_PROGRESS else o.state,
            "items": o.items_raw,
            "customer": o.customer_name,
            "delivery_address": o.delivery_address,
            "payment_method": o.payment_method,
        }
        for o in rows
    ]
    return {"days": days, "state": state, "count": len(items), "items": items}


async def list_products(db: AsyncSession, user: User, args: dict) -> dict:
    q = select(Product).where(Product.advertiser_id == user.id)
    if not args.get("include_hidden"):
        q = q.where(Product.active.is_(True))
    if query := (args.get("query") or "").strip():
        q = q.where(Product.name.ilike(f"%{query}%"))
    rows = (await db.execute(q.order_by(Product.name).limit(_MAX_LIST))).scalars().all()
    items = [
        {
            "id": str(p.id),
            "name": p.name,
            "price": float(p.price) if p.price is not None else None,
            "active": p.active,
            "has_photo": bool(p.photo_url),
        }
        for p in rows
    ]
    return {"count": len(items), "items": items}


async def get_bot_status(db: AsyncSession, user: User, args: dict) -> dict:
    n_products, n_priced = (await db.execute(
        select(func.count(Product.id), func.count(Product.price))
        .where(Product.advertiser_id == user.id, Product.active.is_(True))
    )).one()
    docs = (await db.execute(
        select(func.count(KnowledgeBase.id)).where(
            KnowledgeBase.advertiser_id == user.id,
            KnowledgeBase.is_active.is_(True),
            KnowledgeBase.processing_status == "done",
        )
    )).scalar_one()
    hours = render_hours(_clean_hours(user.business_hours)) if user.business_hours else None
    page_url = f"{(settings.FRONTEND_URL or '').rstrip('/')}/sitio/{user.slug}" if user.slug else None
    missing = []
    if not user.bot_instructions:
        missing.append("instrucciones del bot (qué vende, políticas, formas de pago)")
    if not n_products:
        missing.append("productos o servicios en el catálogo")
    elif n_products > n_priced:
        missing.append(f"precio en {n_products - n_priced} producto(s)")
    if not hours:
        missing.append("horario de atención")
    if not docs:
        missing.append("documentos de conocimiento (opcional)")
    if not user.slug:
        missing.append("página publicada")
    if user.meta_connection_status != "connected":
        missing.append("WhatsApp conectado (el bot aún no atiende por WhatsApp)")
    return {
        "business_name": user.business_name,
        "bot_name": user.bot_name,
        "has_instructions": bool(user.bot_instructions),
        "products": n_products,
        "products_without_price": n_products - n_priced,
        "hours": hours,
        "documents": docs,
        "page_url": page_url,
        "whatsapp_connected": user.meta_connection_status == "connected",
        "web_agent_enabled": bool(user.customer_agent_enabled),
        "loyalty_reward": (user.loyalty_config or {}).get("reward") or None,
        "missing": missing,
    }


async def ask_bot(db: AsyncSession, user: User, args: dict) -> dict:
    question = _clean_text(args.get("question"), 300)
    if not question:
        return {"error": "Dime qué le pregunto al bot."}
    # Mismo camino que un cliente real; sin conversation_key no cuenta como conversación del plan.
    from app.services.rag_service import answer_with_rag

    answer = await answer_with_rag(
        advertiser_id=str(user.id),
        query=question,
        conversation_history=[],
        db=db,
        business_name=user.business_name or "el negocio",
        bot_name=user.bot_name or "Asistente",
        bot_personality=user.bot_personality or "amigable y profesional",
    )
    return {"question": question, "answer": answer}


async def open_page_builder(db: AsyncSession, user: User, args: dict) -> dict:
    if user.role != "advertiser":
        return {"error": "Solo los negocios pueden armar su página."}
    if user.slug:
        out = {"has_page": True, "page_url": f"{(settings.FRONTEND_URL or '').rstrip('/')}/sitio/{user.slug}"}
        # Quiere cambiarla: el armador se abre con lo que ya tiene (ver /public/onboarding/mine).
        return {**out, "edit": True} if args.get("edit") is True else out
    return {"has_page": False}


async def run_read_tool(db: AsyncSession, user: User, tool_name: str, args: dict) -> dict:
    if tool_name == "open_page_builder":
        return await open_page_builder(db, user, args)
    if tool_name == "list_appointments":
        return await list_appointments(db, user, args)
    if tool_name == "list_orders":
        return await list_orders(db, user, args)
    if tool_name == "get_bot_status":
        return await get_bot_status(db, user, args)
    if tool_name == "test_bot":
        return await ask_bot(db, user, args)
    return await list_products(db, user, args)


# ─── Cambios: vista previa (lo que el dueño confirma) y ejecución ─────────────

_INFO_HEADERS = {"faqs": "Preguntas frecuentes", "policies": "Políticas", "notes": "Otros datos"}

# Mismos colores que ofrece el armador de la página, más algunos comunes.
_COLORS = {
    "verde": "#2f9e44", "azul": "#1c7ed6", "morado": "#7048e8", "rojo": "#e03131", "naranja": "#e8590c",
    "rosa": "#d6336c", "amarillo": "#f59f00", "turquesa": "#0c8599", "cafe": "#8a5a2b",
}
_THEMES = ("medianoche", "pizarra", "esmeralda", "claro", "crema")
_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _resolve_color(value) -> str | None:
    text = (_clean_text(value, 30) or "").lower()
    text = text.translate(str.maketrans("áéíóú", "aeiou")).removeprefix("color ").strip()
    if text in _COLORS:
        return _COLORS[text]
    if _HEX_RE.match(text):
        if len(text) == 4:
            text = "#" + "".join(c * 2 for c in text[1:])
        return text.lower()
    return None


def _clean_info_ops(args: dict) -> dict:
    ops: dict = {}
    for key, limit in (("address", 300), ("city", 100)):
        if value := _clean_text(args.get(key), limit):
            ops[key] = value
    for key, field, limit in (("payment_methods", "payment_methods", 100), ("add_policies", "add_policies", 200),
                              ("add_notes", "add_notes", 200), ("remove_faqs", "remove_faqs", 200)):
        raw = args.get(key)
        items = [t for x in (raw if isinstance(raw, list) else [])[:12] if (t := _clean_text(x, limit))]
        if items:
            ops[field] = items
    faqs = []
    for f in (args.get("add_faqs") if isinstance(args.get("add_faqs"), list) else [])[:6]:
        if isinstance(f, dict) and (q := _clean_text(f.get("q"), 200)) and (a := _clean_text(f.get("a"), 400)):
            faqs.append({"q": q, "a": a})
    if faqs:
        ops["add_faqs"] = faqs
    return ops


def _apply_info_ops(current: dict, ops: dict) -> tuple[dict, list[str]]:
    """Solo los temas que cambian (para fusionarlos) y cómo decirlos."""
    changed: dict = {}
    parts: list[str] = []
    if "address" in ops or "city" in ops:
        address, city = ops.get("address", current["address"]), ops.get("city", current["city"])
        if (address, city) != (current["address"], current["city"]):
            changed["address"], changed["city"] = address, city
            parts.append("ubicación a " + ", ".join(x for x in (address, city) if x))
    if ops.get("payment_methods") and ops["payment_methods"] != current["payment_methods"]:
        changed["payment_methods"] = ops["payment_methods"]
        parts.append("formas de pago: " + ", ".join(ops["payment_methods"]))
    faqs = [f for f in current["faqs"]
            if not any(r.lower() in f["q"].lower() for r in ops.get("remove_faqs", []))]
    known = {f["q"].lower() for f in faqs}
    faqs += [f for f in ops.get("add_faqs", []) if f["q"].lower() not in known]
    if faqs != current["faqs"]:
        changed["faqs"] = faqs
        gone = len([f for f in current["faqs"] if f not in faqs])
        new = len([f for f in faqs if f not in current["faqs"]])
        parts.append("preguntas frecuentes" + (f" (+{new})" if new else "") + (f" (−{gone})" if gone else ""))
    for key, op, label in (("policies", "add_policies", "políticas"), ("notes", "add_notes", "otros datos")):
        merged = current[key] + [x for x in ops.get(op, []) if x.lower() not in {y.lower() for y in current[key]}]
        if merged != current[key]:
            changed[key] = merged
            parts.append(f"{label} (+{len(merged) - len(current[key])})")
    return changed, parts


def _current_info(user: User) -> dict:
    from app.services.owner_signup import instructions_info

    parsed, _ = instructions_info(user)
    return parsed

def _sync_instructions_product(user: User, old_name: str, new_name: str, price: Decimal | None) -> None:
    """Si las instrucciones del bot listan este producto ("- Corte — $150"),
    deja esa línea con el nombre y precio nuevos."""
    text = user.bot_instructions or ""
    pattern = re.compile(rf"^- {re.escape(old_name)}( — \$[\d,]+(?:\.\d+)?)?", re.IGNORECASE | re.MULTILINE)
    if not pattern.search(text):
        return
    line = f"- {new_name}" + (f" — {_money(price)}" if price is not None else "")
    user.bot_instructions = pattern.sub(lambda _m: line, text, count=1)


def _sync_instructions_hours(user: User, hours: dict) -> None:
    text = user.bot_instructions or ""
    if re.search(r"^Horario: .*$", text, re.MULTILINE):
        user.bot_instructions = re.sub(
            r"^Horario: .*$", lambda _m: f"Horario: {render_hours(hours)}", text, count=1, flags=re.MULTILINE,
        )


async def preview_change(db: AsyncSession, user: User, tool_name: str, args: dict) -> tuple[str | None, dict | None, str | None]:
    if tool_name == "create_product":
        name = _clean_text(args.get("name"), 200)
        if not name:
            return None, None, "Falta el nombre del producto."
        price = _price(args.get("price"))
        photo = _own_photo(user, args.get("photo_url"))
        resolved = {
            "name": name,
            "price": str(price) if price is not None else None,
            "description": _clean_text(args.get("description"), 1000),
            "category": _clean_text(args.get("category"), 100),
            "photo_url": photo,
        }
        summary = f"Agregar \"{name}\" al catálogo a {_money(price)}" + (" con la foto que mandaste." if photo else ".")
        return summary, resolved, None

    if tool_name == "update_product":
        product = await _find_product(db, user, args.get("product") or "")
        if not product:
            return None, None, f"No encontré un solo producto que se llame \"{args.get('product')}\". Dime el nombre exacto."
        changes: dict = {}
        parts: list[str] = []
        if args.get("price") is not None:
            price = _price(args.get("price"))
            if price is None:
                return None, None, "Ese precio no es válido."
            changes["price"] = str(price)
            parts.append(f"precio de {_money(product.price)} a {_money(price)}")
        new_name = _clean_text(args.get("name"), 200)
        if new_name and new_name != product.name:
            changes["name"] = new_name
            parts.append(f"nombre a \"{new_name}\"")
        if args.get("description") is not None:
            changes["description"] = _clean_text(args.get("description"), 1000)
            parts.append("descripción")
        if args.get("photo_url"):
            photo = _own_photo(user, args.get("photo_url"))
            if not photo:
                return None, None, "No encontré la foto; vuelve a tomarla con el botón de la cámara."
            changes["photo_url"] = photo
            parts.append("foto")
        if isinstance(args.get("active"), bool) and args["active"] != product.active:
            changes["active"] = args["active"]
            parts.append("mostrarlo en el catálogo" if args["active"] else "ocultarlo del catálogo")
        if not changes:
            return None, None, f"\"{product.name}\" ya está así; no hay nada que cambiar."
        summary = f"Cambiar \"{product.name}\": " + ", ".join(parts) + "."
        return summary, {"product_id": str(product.id), "changes": changes}, None

    if tool_name == "update_business_hours":
        raw = args.get("changes")
        if not isinstance(raw, dict) or not raw:
            return None, None, "Dime qué días y en qué horario."
        changes: dict = {}
        for day, rng in raw.items():
            if day not in DAYS:
                return None, None, f"No reconozco el día \"{day}\"."
            if rng is None:
                changes[day] = None
            elif (
                isinstance(rng, list) and len(rng) == 2
                and all(isinstance(h, str) and _HOUR_RE.match(h) for h in rng) and rng[0] < rng[1]
            ):
                changes[day] = [rng[0], rng[1]]
            else:
                return None, None, f"El horario del {DAY_LABELS[day].lower()} no es válido (usa HH:MM, abre antes de cerrar)."
        current = _clean_hours(user.business_hours) or {d: None for d in DAYS}
        new_hours = {d: changes[d] if d in changes else current.get(d) for d in DAYS}
        if not any(new_hours.values()):
            return None, None, "Con ese cambio quedaría cerrado toda la semana; dime al menos un día abierto."
        said = "; ".join(
            f"{DAY_LABELS[d]} {r[0]} a {r[1]}" if r else f"{DAY_LABELS[d]} cerrado" for d, r in changes.items()
        )
        return f"Cambiar el horario: {said}.", {"hours": new_hours}, None

    if tool_name == "set_loyalty_reward":
        reward = _clean_text(args.get("reward"), 120)
        if not reward:
            return None, None, "Dime qué premio gana el cliente al llenar su tarjeta."
        current = {**LOYALTY_DEFAULTS, **(user.loyalty_config or {})}
        stamps = args.get("stamps_required") or current["stamps_required"]
        if not isinstance(stamps, int) or not 3 <= stamps <= 20:
            return None, None, "La tarjeta puede tener de 3 a 20 sellos."
        return (
            f"Tarjeta de lealtad: al juntar {stamps} sellos, tu cliente gana \"{reward}\".",
            {"reward": reward, "stamps_required": stamps},
            None,
        )

    if tool_name == "update_bot_info":
        ops = _clean_info_ops(args)
        if not ops:
            return None, None, "Dime qué cambio: dirección, formas de pago, preguntas frecuentes, políticas u otros datos."
        changed, parts = _apply_info_ops(_current_info(user), ops)
        if not changed:
            return None, None, "Tu bot ya sabe eso; no hay nada que cambiar."
        return "Cambiar lo que sabe tu bot: " + "; ".join(parts) + ".", {"ops": ops}, None

    if tool_name == "update_page_style":
        changes: dict = {}
        parts: list[str] = []
        if args.get("color"):
            color = _resolve_color(args["color"])
            if not color:
                return None, None, f"No reconozco el color \"{args['color']}\". Dime uno como verde, azul, morado, rojo, naranja o rosa."
            if color != (user.widget_color or "").lower():
                changes["color"] = color
                parts.append(f"color a {args['color'].strip()}")
        if args.get("theme"):
            theme = (_clean_text(args["theme"], 30) or "").lower()
            if theme not in _THEMES:
                return None, None, "El fondo puede ser medianoche, pizarra, esmeralda, claro o crema."
            if theme != (user.site_theme or "medianoche"):
                changes["theme"] = theme
                parts.append(f"fondo a {theme}")
        if not changes:
            return None, None, "Tu página ya está así; dime qué color o fondo quieres."
        return "Cambiar tu página: " + ", ".join(parts) + ".", changes, None

    return None, None, "No reconozco esa acción."


async def execute_change(db: AsyncSession, user: User, tool_name: str, args: dict) -> tuple[dict | None, str | None]:
    if tool_name == "create_product":
        price = _price(args.get("price"))
        product = Product(
            advertiser_id=user.id,
            name=args["name"],
            price=price,
            description=args.get("description"),
            category=args.get("category"),
            photo_url=_own_photo(user, args.get("photo_url")),
            active=True,
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)
        logger.info("[COPILOT] product created %s by %s", product.id, user.id)
        return {"product_id": str(product.id), "name": product.name, "price": float(price) if price is not None else None,
                "has_photo": bool(product.photo_url)}, None

    if tool_name == "update_product":
        try:
            pid = uuid.UUID(str(args.get("product_id")))
        except ValueError:
            return None, "Ese producto no es válido."
        product = (await db.execute(
            select(Product).where(Product.id == pid, Product.advertiser_id == user.id)
        )).scalar_one_or_none()
        if not product:
            return None, "Ese producto ya no existe."
        changes = args.get("changes") or {}
        old_name = product.name
        if "price" in changes:
            product.price = _price(changes["price"])
        if "name" in changes:
            product.name = changes["name"]
        if "description" in changes:
            product.description = changes["description"]
        if "photo_url" in changes:
            product.photo_url = _own_photo(user, changes["photo_url"])
        if "active" in changes:
            product.active = bool(changes["active"])
        if "price" in changes or "name" in changes:
            _sync_instructions_product(user, old_name, product.name, product.price)
            db.add(user)
        await db.commit()
        logger.info("[COPILOT] product %s updated by %s: %s", product.id, user.id, sorted(changes))
        return {"product_id": str(product.id), "name": product.name,
                "price": float(product.price) if product.price is not None else None,
                "active": product.active, "changed": sorted(changes)}, None

    if tool_name == "update_business_hours":
        hours = _clean_hours(args.get("hours"))
        if not hours:
            return None, "Ese horario no es válido."
        user.business_hours = hours
        _sync_instructions_hours(user, hours)
        db.add(user)
        await db.commit()
        logger.info("[COPILOT] business hours updated by %s", user.id)
        return {"hours": render_hours(hours)}, None

    if tool_name == "set_loyalty_reward":
        reward = _clean_text(args.get("reward"), 120)
        stamps = args.get("stamps_required")
        if not reward or not isinstance(stamps, int) or not 3 <= stamps <= 20:
            return None, "Ese premio no es válido."
        user.loyalty_config = {"enabled": True, "stamps_required": stamps, "reward": reward}
        db.add(user)
        await db.commit()
        logger.info("[COPILOT] loyalty reward set by %s", user.id)
        return {"reward": reward, "stamps_required": stamps}, None

    if tool_name == "update_bot_info":
        # Se vuelve a leer lo que hay al confirmar: si cambió mientras tanto, no se pisa.
        ops = _clean_info_ops(args.get("ops") or {})
        changed, parts = _apply_info_ops(_current_info(user), ops)
        if not changed:
            return None, "Tu bot ya sabe eso; no hay nada que cambiar."
        if changed.get("city"):
            user.city = changed["city"]
        drop = {_INFO_HEADERS[k] for k in _INFO_HEADERS if k in changed and not changed[k]}
        user.bot_instructions = merge_instructions(user.bot_instructions, changed, drop)
        db.add(user)
        await db.commit()
        logger.info("[COPILOT] bot info updated by %s: %s", user.id, sorted(changed))
        return {"changed": parts}, None

    if tool_name == "update_page_style":
        color = _resolve_color(args.get("color")) if args.get("color") else None
        theme = args.get("theme") if args.get("theme") in _THEMES else None
        if not color and not theme:
            return None, "Ese cambio no es válido."
        if color:
            user.widget_color = color
        if theme:
            user.site_theme = theme
        db.add(user)
        await db.commit()
        logger.info("[COPILOT] page style updated by %s", user.id)
        return {"color": color, "theme": theme}, None

    return None, "No reconozco esa acción."


def summarize(tool_name: str, data: dict) -> str:
    if tool_name == "list_appointments":
        return f"Encontré {data.get('count', 0)} cita(s)."
    if tool_name == "list_orders":
        return f"Encontré {data.get('count', 0)} pedido(s)."
    if tool_name == "list_products":
        return f"Encontré {data.get('count', 0)} producto(s)."
    if tool_name == "get_bot_status":
        return f"Revisé tu bot: le falta {len(data.get('missing', []))} cosa(s)."
    if tool_name == "test_bot":
        return "Probé tu bot con esa pregunta."
    if tool_name == "open_page_builder":
        if data.get("edit"):
            return "Abrí el armador con lo que ya tiene tu página."
        return "Tu página ya está publicada." if data.get("has_page") else "Abrí el armador de tu página."
    if tool_name == "update_page_style":
        return "Tu página ya tiene el nuevo " + ("color" if data.get("color") else "fondo") + "."
    if tool_name == "update_bot_info":
        return "Tu bot ya sabe lo nuevo: " + "; ".join(data.get("changed", [])) + "."
    if tool_name == "create_product":
        return f"Producto \"{data.get('name', '')}\" agregado al catálogo ({_money(data.get('price'))})."
    if tool_name == "update_product":
        return f"Producto \"{data.get('name', '')}\" actualizado."
    if tool_name == "update_business_hours":
        return f"Horario actualizado: {data.get('hours', '')}."
    if tool_name == "set_loyalty_reward":
        return f"Tarjeta de lealtad lista: {data.get('stamps_required')} sellos = \"{data.get('reward', '')}\"."
    return tool_name
