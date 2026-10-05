"""
A quién le llega una campaña y por dónde, antes de enviarla.

Los clientes que activaron las notificaciones en su portal reciben la campaña
gratis como notificación web (campaign_ops._push_campaign); los demás, por
WhatsApp, que Meta cobra. El dueño ve el reparto y lo que costaría antes de
apretar "Enviar", y puede elegir mandarla solo por web.
"""
import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.contact import Contact
from app.services.web_push import contacts_with_push

# Lo que Meta cobra por mensaje de marketing entregado en México desde el
# 1-oct-2026 (USD 0.0397), en pesos a un tipo de cambio redondo. Es un tope:
# los mensajes dentro de la ventana de 24 h cuestan menos o nada.
META_MARKETING_USD_MX = 0.0397
USD_TO_MXN = 18.5

# Modos que sí se mandan como notificación web. La radio también: el aviso
# abre la promo en la tarjeta del cliente, que trae el audio para escucharlo
# ahí (2026-10-05). Las Voces del Barrio siguen solo por WhatsApp.
WEB_MODES = ("regular", "banner", "radio", "comunitaria")


def recipients_query(campaign: Campaign) -> Select:
    """Los contactos a los que va la campaña según su segmento."""
    q = select(Contact).where(
        Contact.advertiser_id == campaign.advertiser_id,
        Contact.status == "active",
    )
    segment = campaign.segment or {}
    specific_ids = segment.get("specific_contacts", [])
    tags = segment.get("tags", [])
    if specific_ids:
        q = q.where(Contact.id.in_([uuid.UUID(str(c)) for c in specific_ids]))
    elif tags:
        q = q.where(Contact.tags.overlap(tags))
    return q


def supports_web(campaign: Campaign) -> bool:
    mode = (campaign.ab_test or {}).get("campaign_mode", "regular")
    return mode in WEB_MODES and campaign.type != "voces"


def is_web_only(campaign: Campaign) -> bool:
    return bool((campaign.ab_test or {}).get("web_only")) and supports_web(campaign)


async def campaign_reach(db: AsyncSession, campaign: Campaign) -> dict:
    """Cuántos la recibirían gratis por web y cuántos por WhatsApp. Los que
    hoy no se pueden contactar (sin actividad, en pausa de 48 h…) no cuentan
    en ninguno de los dos, igual que al enviar."""
    from app.workers.task_helpers.campaign_ops import _is_contact_active

    contacts = (await db.execute(recipients_query(campaign))).scalars().all()
    reachable = [c for c in contacts if _is_contact_active(c)[0]]
    web_ok = supports_web(campaign)
    with_push = await contacts_with_push(db, [c.id for c in reachable]) if web_ok else set()
    web = sum(1 for c in reachable if c.id in with_push)
    whatsapp = len(reachable) - web
    return {
        "total": len(reachable),
        "web": web,
        "whatsapp": whatsapp,
        "whatsapp_cost_mxn": round(whatsapp * META_MARKETING_USD_MX * USD_TO_MXN, 2),
        "web_supported": web_ok,
    }
