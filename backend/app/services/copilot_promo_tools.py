"""
Copiloto: crear y mandar una promo desde el chat (send_promo) — Fase 2 de
campañas simples (docs/specs/2026-10-28-copiloto-crea-promos.md).

La vista previa arma el mensaje con el catálogo real (el mismo generador que
la campaña en 3 toques de la web), resuelve a quién le llega y dice por dónde;
el texto exacto que vio el dueño va firmado en la confirmación y es el que se
manda. Por defecto sale gratis por web; WhatsApp solo si el dueño lo pidió con
palabras y tiene su chip conectado (Meta le cobra a su tarjeta).
"""
import logging
import re
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.campaign_actions import (
    CampaignContentIncompleteError,
    CampaignValidationError,
    check_content_complete,
    validate_new_campaign,
)
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.user import User
from app.services.analytics_service import capture_event
from app.services.campaign_reach import campaign_reach, whatsapp_connected

logger = logging.getLogger(__name__)

NAME = "send_promo"
BOUGHT_DAYS = 90
_AUDIENCES = ("all", "bought", "one")

TOOL = {
    "name": NAME,
    "description": (
        "Crea y manda una promoción nueva a los clientes del negocio. Úsala cuando el dueño pida "
        "'manda una promo de…', 'anuncia que…', 'avísales a mis clientes de…'. El sistema arma el "
        "mensaje con el catálogo real y le pide confirmación al dueño antes de mandar — llámala "
        "directo, sin redactar tú el mensaje ni preguntar antes. Si el dueño pide cambios a una "
        "promo que le enseñaste ('más corta', 'quítale el precio'), llámala otra vez con `message` "
        "ya corregido. Va gratis por web; whatsapp=true SOLO si el dueño dijo 'por WhatsApp'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "what": {"type": "string", "description": "Qué quiere anunciar, con sus palabras (ej. '2x1 en fundas este viernes')."},
            "audience": {
                "type": "string",
                "enum": list(_AUDIENCES),
                "description": "all = todos (por defecto); bought = los que le compraron hace poco; one = un solo cliente.",
            },
            "contact": {"type": "string", "description": "Nombre o teléfono del cliente cuando audience = one."},
            "discount_percent": {
                "type": "integer",
                "description": "Solo si el dueño dijo un porcentaje (ej. 'con 15%' → 15). '2x1' no es descuento. Si no lo dijo, no lo mandes.",
            },
            "whatsapp": {"type": "boolean", "description": "true solo si el dueño pidió mandarla por WhatsApp."},
            "message": {
                "type": "string",
                "description": "Texto exacto a mandar, solo si el dueño lo dictó o pidió cambiar la versión que le enseñaste.",
            },
        },
        "required": ["what"],
    },
}


def _last4(phone: str) -> str:
    return (phone or "")[-4:]


def campaign_name(what: str) -> str:
    clean = " ".join(what.split())
    name = clean[:1].upper() + clean[1:]
    return name if len(name) <= 60 else f"{name[:57].rstrip()}…"


async def _resolve_one(db: AsyncSession, user: User, who: str) -> tuple[Contact | None, str | None]:
    who = who.strip()
    if not who:
        return None, "¿A qué cliente se la mando? Dime su nombre o teléfono."
    like = f"%{who}%"
    rows = (await db.execute(
        select(Contact)
        .where(Contact.advertiser_id == user.id, Contact.status == "active",
               or_(Contact.name.ilike(like), Contact.phone.ilike(like)))
        .order_by(Contact.name)
        .limit(6)
    )).scalars().all()
    if not rows:
        return None, f"No encontré a «{who}» entre tus clientes."
    exact = [c for c in rows if c.name.strip().lower() == who.lower()]
    if len(exact) == 1:
        return exact[0], None
    if len(rows) > 1:
        names = ", ".join(f"{c.name} (…{_last4(c.phone)})" for c in rows[:5])
        return None, f"Hay varios clientes que coinciden con «{who}»: {names}. ¿A cuál se la mando?"
    return rows[0], None


def _discount(raw) -> tuple[int, str | None]:
    if raw in (None, "", 0):
        return 0, None
    try:
        pct = int(raw)
    except (TypeError, ValueError):
        return 0, "El descuento debe ser un número, por ejemplo 15."
    if not 1 <= pct <= 90:
        return 0, "El descuento debe ser de 1% a 90%."
    return pct, None


def keep_asked_discount(args: dict, owner_texts: list[str]) -> dict:
    """El descuento solo se queda si el dueño lo dijo ("15%", "15 por ciento",
    "descuento de 15"). Pasó con la IA real: "promo de 2x1" salió con 2% de
    descuento que nadie pidió."""
    raw = args.get("discount_percent")
    if raw in (None, "", 0):
        return args
    try:
        pct = int(raw)
    except (TypeError, ValueError):
        return {**args, "discount_percent": None}
    said = " ".join(owner_texts).lower()
    patterns = (rf"\b{pct}\s*(%|por\s*ciento)", rf"descuento\D{{0,15}}\b{pct}\b", rf"\b{pct}\b\D{{0,15}}descuento")
    if any(re.search(p, said) for p in patterns):
        return args
    return {**args, "discount_percent": None}


_WHATSAPP_WORDS = re.compile(r"whats|wats|guasap|wasap|wpp|\bwa\b")


def keep_asked_whatsapp(args: dict, owner_texts: list[str]) -> dict:
    """WhatsApp (Meta le cobra al dueño) solo si él lo nombró; no basta con
    que la IA lo diga, igual que con el descuento."""
    if args.get("whatsapp") and not _WHATSAPP_WORDS.search(" ".join(owner_texts).lower()):
        return {**args, "whatsapp": False}
    return args


def _ab_test(discount: int, web_only: bool) -> dict:
    ab: dict = {"enabled": False, "campaign_mode": "regular"}
    if discount:
        ab.update(has_coupon=True, coupon_description=f"{discount}% de descuento", coupon_percent=discount, coupon_hours=72)
    if web_only:
        ab["web_only"] = True
    return ab


def _pesos(n: float) -> str:
    return f"${n:,.0f}" if float(n).is_integer() else f"${n:,.2f}"


def _clientes(n: int) -> str:
    return f"{n} {'cliente' if n == 1 else 'clientes'}"


def reach_line(reach: dict, web_only: bool) -> str:
    """"A 2 les suena aviso · 5 la ven en su chat · 3 por WhatsApp (Meta te cobra aprox $2)"."""
    parts = []
    ring = reach["web"] - reach.get("web_silent", 0)
    chat = reach.get("web_silent", 0) + (reach.get("web_chat", 0) if web_only else 0)
    if ring > 0:
        parts.append(f"a {_clientes(ring)} les suena aviso")
    if chat > 0:
        parts.append(f"{_clientes(chat)} la ven en su chat")
    if not web_only and reach["whatsapp"] > 0:
        parts.append(f"{_clientes(reach['whatsapp'])} por WhatsApp (Meta te cobra aprox {_pesos(reach['whatsapp_cost_mxn'])})")
    return " · ".join(parts)


async def preview(db: AsyncSession, user: User, args: dict) -> tuple[str | None, dict | None, str | None]:
    from app.services.claude_service import generate_campaign_variants
    from app.services.rag_service import catalog_context

    what = (args.get("what") or "").strip()
    if not what:
        return None, None, "¿Qué quieres anunciar?"
    audience = args.get("audience") or "all"
    if audience not in _AUDIENCES:
        audience = "all"

    segment: dict = {}
    who = ""
    if audience == "bought":
        segment = {"bought_days": BOUGHT_DAYS}
    elif audience == "one":
        contact, error = await _resolve_one(db, user, str(args.get("contact") or ""))
        if error:
            return None, None, error
        segment = {"specific_contacts": [str(contact.id)]}
        who = f"{contact.name} (…{_last4(contact.phone)})"

    discount, error = _discount(args.get("discount_percent"))
    if error:
        return None, None, error

    try:
        validate_new_campaign(user, name=campaign_name(what), message_text="-", type_="promo",
                              status="draft", segment=segment)
    except CampaignValidationError as e:
        return None, None, e.detail

    connected = whatsapp_connected(user)
    wants_whatsapp = bool(args.get("whatsapp"))
    web_only = not (wants_whatsapp and connected)

    probe = Campaign(advertiser_id=user.id, name="", type="promo", message_text="", segment=segment,
                     ab_test={"campaign_mode": "regular"})
    reach = await campaign_reach(db, probe)
    reachable = reach["web"] + reach["web_chat"] + (0 if web_only else reach["whatsapp"])
    if reachable == 0:
        if audience == "bought":
            return None, None, f"Nadie te ha comprado en los últimos {BOUGHT_DAYS} días (con \"Cobré\" o pedido), así que no hay a quién mandarla."
        return None, None, "Todavía no tienes clientes a quién mandarle la promo."

    message = (args.get("message") or "").strip()
    if not message:
        try:
            variants = await generate_campaign_variants(
                campaign_type="promo", business_name=user.business_name or "", intent=what,
                catalog=await catalog_context(db, str(user.id)),
            )
        except Exception:
            logger.warning("[COPILOT] promo generation failed user=%s", user.id, exc_info=True)
            variants = []
        message = next((v.strip() for v in variants if v and v.strip()), "")
        if not message:
            return None, None, "No pude armar el mensaje ahorita. Intenta de nuevo o dime el texto exacto."

    to = who or ("los que te compraron en los últimos 90 días" if audience == "bought" else "todos tus clientes")
    # A quién, por dónde y el costo van ANTES del mensaje: WhatsApp corta el texto de los botones
    # a 1024 caracteres y la línea de lo que cobra Meta no se puede perder.
    lines = [f"Promo para {to}.", f"Le llega: {reach_line(reach, web_only)}."]
    if wants_whatsapp and not connected:
        lines.append("Tu WhatsApp no está conectado, así que va solo por web (gratis). Conecta tu chip en Configuración para mandar por WhatsApp.")
    elif web_only:
        lines.append("Va gratis por web, sin WhatsApp.")
    if discount:
        lines.append(f"🎟️ Con cupón de {discount}% de descuento.")
    lines += ["", f"«{message}»"]
    summary = "\n".join(lines)

    resolved = {
        "name": campaign_name(what),
        "message": message,
        "segment": segment,
        "discount_percent": discount,
        "web_only": web_only,
        # Una sola campaña por vista previa, aunque el "sí" llegue dos veces.
        "key": uuid.uuid4().hex,
    }
    return summary, resolved, None


async def start_campaign(db: AsyncSession, user: User, campaign: Campaign, web_only: bool, source: str) -> str | None:
    """Arranca el envío (lo mismo que POST /campaigns/{id}/resume): None si
    salió, o la frase de por qué no. web_only queda guardado en la campaña
    para que el envío (que corre aparte) lo respete."""
    from app.services.send_block_explain import preflight_campaign_send
    from app.workers.tasks import schedule_campaign

    try:
        check_content_complete(campaign)
    except CampaignContentIncompleteError as e:
        return str(e)
    blocked = await preflight_campaign_send(db, campaign, user, web_only=web_only)
    if blocked:
        return blocked
    ab = {k: v for k, v in (campaign.ab_test or {}).items() if k != "web_only"}
    campaign.ab_test = {**ab, "web_only": True} if web_only else ab
    campaign.status = "running"
    await db.commit()
    schedule_campaign.delay(str(campaign.id))
    capture_event("campaign_sent", user_id=user.id, properties={
        "campaign_id": str(campaign.id), "type": campaign.type, "source": source, "web_only": web_only,
    })
    return None


async def execute(db: AsyncSession, user: User, args: dict) -> tuple[dict | None, str | None]:
    segment = args.get("segment") or {}
    message = (args.get("message") or "").strip()
    name = args.get("name") or "Promo"
    web_only = bool(args.get("web_only", True))
    if not web_only and not whatsapp_connected(user):
        web_only = True  # se desconectó entre la vista previa y el "sí"
    try:
        validate_new_campaign(user, name=name, message_text=message, type_="promo", status="draft", segment=segment)
    except CampaignValidationError as e:
        return None, e.detail

    key = str(args.get("key") or "")
    if key:
        existing = (await db.execute(
            select(Campaign.id).where(Campaign.advertiser_id == user.id, Campaign.ab_test["copilot_key"].astext == key)
        )).first()
        if existing:
            return None, "Esa promo ya se mandó."

    ab = _ab_test(int(args.get("discount_percent") or 0), web_only)
    if key:
        ab["copilot_key"] = key
    campaign = Campaign(
        advertiser_id=user.id, name=name, type="promo", message_text=message, segment=segment,
        ab_test=ab, status="draft",
    )
    db.add(campaign)
    await db.flush()
    error = await start_campaign(db, user, campaign, web_only, source="copilot_promo")
    if error:
        await db.commit()  # queda como borrador en Campañas, para mandarla después
        return None, f"{error} La promo quedó guardada como borrador en Campañas."
    return {"campaign_id": str(campaign.id), "name": name, "web_only": web_only, "status": "running"}, None


def summarize(data: dict) -> str:
    how = "gratis por web" if data.get("web_only") else "por web y WhatsApp"
    return f"Promo \"{data.get('name', '')}\" enviada {how}."

