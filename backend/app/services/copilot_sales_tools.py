"""Cobrar hablándole al Copiloto: "cobré 85 a Ana", "vendí 120", "deshacer"
(spec docs/specs/2026-10-17-cobrar-con-copiloto.md).

Se guardan directo, sin la tarjeta de confirmación (decisión del dueño: en
el mostrador hay fila); para eso está "deshacer" (15 min, igual que la
pantalla Cobrar, sirve con cualquier cobro de hoy). Si el cliente no queda claro, no se guarda nada y el
Copiloto pregunta.
"""
import logging
import re

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.contact import validate_phone_e164
from app.services import sales_service
from app.services.sales_service import SaleError

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "name": "record_sale",
        "description": (
            "Registra un cobro que el dueño YA hizo en su negocio (\"cobré 85 a Ana\", \"vendí 120\", "
            "\"me pagaron 300 de Juan\"). Se guarda de inmediato, sin pedir confirmación, y le pone su "
            "sello de lealtad al cliente. Sin cliente si el dueño no lo menciona. NO es para fiados ni "
            "deudas (\"me debe 50\"): solo lo que ya le pagaron. Si el resultado trae "
            "`choices`, pregunta cuál cliente es; si trae `not_found`, ofrece registrarlo sin cliente o "
            "darlo de alta con su teléfono."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Cuánto cobró, en pesos (ej. 85)."},
                "customer": {
                    "type": "string",
                    "description": "Nombre del cliente o últimos dígitos de su teléfono, tal como lo dijo el dueño.",
                },
                "customer_phone": {
                    "type": "string",
                    "description": "Solo para dar de alta a un cliente nuevo: su WhatsApp a 10 dígitos.",
                },
            },
            "required": ["amount"],
        },
    },
    {
        "name": "get_sales_today",
        "description": (
            "Cuánto ha cobrado hoy el negocio (total y número de ventas registradas). Úsalo para "
            "\"¿cuánto llevo hoy?\", \"¿cuánto vendí hoy?\"."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "undo_sale",
        "description": (
            "Borra un cobro de hoy y el sello que dio. Sin datos borra el último (\"deshacer\", "
            "\"me equivoqué\"); si el dueño dice cuál (\"borra el de 50\", \"el de Ana\"), manda el "
            "monto y/o el cliente. Si el resultado trae `choices`, pregunta cuál de esos es."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Monto del cobro a borrar, si lo dijo."},
                "customer": {"type": "string", "description": "Nombre o últimos dígitos del cliente, si lo dijo."},
            },
            "required": [],
        },
    },
]
NAMES = {t["name"] for t in TOOLS}

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# "don Juan", "la señora Mari": el dueño los nombra así, pero se guardan como "Juan Pérez".
_COURTESY = re.compile(r"^((la|el|al|a)\s+)?((don|doña|dona|señora|senora|señor|senor|seño|seno|sra\.?|sr\.?|srita\.?)\s+)", re.IGNORECASE)


def _amount_from(raw) -> str:
    """El modelo a veces manda "85 pesos" en vez de 85."""
    if isinstance(raw, (int, float)):
        return str(raw)
    match = _NUMBER.search(str(raw or ""))
    return match.group(0) if match else str(raw or "")


def _money(value) -> int | float:
    """85 y no 85.0: el modelo copia el número tal cual ("Cobré 85.0 pesos")."""
    value = round(float(value), 2)
    return int(value) if value.is_integer() else value


def _pesos(value) -> str:
    """$20, $1,250 o $20.50 — como en el chat, sin ".00" de sobra."""
    value = _money(value or 0)
    return f"${value:,}" if isinstance(value, int) else f"${value:,.2f}"


def _who(c) -> dict:
    return {"name": c.name, "phone_last4": (c.phone or "")[-4:]}


async def record_sale(db: AsyncSession, user: User, args: dict) -> dict:
    from app.services.loyalty_service import notify_stamp

    try:
        amount = sales_service.parse_amount(_amount_from(args.get("amount")))
    except SaleError as e:
        return {"error": str(e)}

    name = _COURTESY.sub("", (args.get("customer") or "").strip()).strip()
    phone = (args.get("customer_phone") or "").strip()
    customer = None
    if phone:
        try:
            phone = validate_phone_e164(phone)
        except (ValueError, ValidationError) as e:
            return {"error": str(e)}
        try:
            customer = await sales_service.find_or_create_customer(db, user, name, phone)
        except SaleError as e:
            return {"error": str(e)}
    elif name:
        matches = await sales_service.find_customers(db, user, name)
        exact = [c for c in matches if c.name.strip().lower() == name.lower()]
        if len(exact) == 1:
            customer = exact[0]
        elif len(matches) == 1:
            customer = matches[0]
        elif matches:
            return {"saved": False, "choices": [_who(c) for c in matches[:5]],
                    "note": "No guardé nada: hay varios clientes así. Pregunta cuál."}
        else:
            return {"saved": False, "not_found": name,
                    "note": "No guardé nada: no hay un cliente así. Ofrece sin cliente o darlo de alta con su teléfono."}

    sale, stamped = await sales_service.record_counter_sale(db, user, amount, customer.id if customer else None)
    await db.commit()
    if stamped:
        await notify_stamp(db, user, customer.id)
    today = await sales_service.today_summary(db, user)
    logger.info("[COPILOT] sale recorded owner=%s amount=%s customer=%s", user.id, amount, bool(customer))
    return {
        "saved": True,
        "amount": _money(sale.amount),
        "customer": _who(customer) if customer else None,
        "stamped": stamped,
        "today_total": _money(today["total"]),
        "today_count": today["count"],
    }


def _sale_line(sale, contact) -> dict:
    from app.services.availability_service import TZ

    return {"amount": _money(sale.amount), "customer": contact.name if contact else None,
            "time": sale.created_at.astimezone(TZ).strftime("%H:%M")}


async def undo_sale(db: AsyncSession, user: User, args: dict) -> dict:
    sales = await sales_service.today_counter_sales(db, user)
    if not sales:
        return {"undone": False, "note": "No hay cobros de hoy que borrar."}
    raw_amount = args.get("amount")
    who = _COURTESY.sub("", (args.get("customer") or "").strip()).strip().lower()
    digits = "".join(ch for ch in who if ch.isdigit())
    matches = sales
    if raw_amount not in (None, ""):
        try:
            amount = sales_service.parse_amount(_amount_from(raw_amount))
        except SaleError as e:
            return {"undone": False, "note": str(e)}
        matches = [(s, c) for s, c in matches if s.amount == amount]
    if who:
        matches = [
            (s, c) for s, c in matches
            if c is not None and (who in c.name.lower() or (len(digits) >= 3 and (c.phone or "").endswith(digits)))
        ]
    if not matches:
        return {"undone": False, "note": "No encontré un cobro así hoy.",
                "choices": [_sale_line(s, c) for s, c in sales[:5]]}
    if (raw_amount not in (None, "") or who) and len(matches) > 1:
        return {"undone": False, "choices": [_sale_line(s, c) for s, c in matches[:5]],
                "note": "No borré nada: hay varios cobros así hoy. Pregunta cuál."}
    sale, contact = matches[0]
    line = _sale_line(sale, contact)
    try:
        await sales_service.undo_sale(db, user, sale.id)
    except SaleError as e:
        return {"undone": False, "note": str(e)}
    await db.commit()
    today = await sales_service.today_summary(db, user)
    return {"undone": True, "amount": line["amount"], "customer": line["customer"],
            "today_total": _money(today["total"]), "today_count": today["count"]}


async def run(db: AsyncSession, user: User, tool_name: str, args: dict) -> dict:
    if tool_name == "record_sale":
        return await record_sale(db, user, args)
    if tool_name == "get_sales_today":
        today = await sales_service.today_summary(db, user)
        return {"today_total": _money(today["total"]), "today_count": today["count"]}
    return await undo_sale(db, user, args)


def summarize(tool_name: str, data: dict) -> str:
    if tool_name == "record_sale":
        if not data.get("saved"):
            return "No guardé el cobro: falta saber el cliente."
        who = f" a {data['customer']['name']}" if data.get("customer") else ""
        return f"Cobro de {_pesos(data.get('amount'))}{who} guardado."
    if tool_name == "get_sales_today":
        return f"Hoy: {_pesos(data.get('today_total'))} en {data.get('today_count', 0)} venta(s)."
    if data.get("undone"):
        who = f" de {data['customer']}" if data.get("customer") else ""
        return f"Cobro de {_pesos(data.get('amount'))}{who} borrado."
    return data.get("note") or "No había cobro que borrar."
