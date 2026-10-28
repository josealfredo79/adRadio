"""
A quién le llega una campaña y por dónde, antes de enviarla.

Los clientes que activaron las notificaciones en su portal reciben la campaña
gratis como notificación web (campaign_ops._push_campaign); los demás, por
WhatsApp, que Meta cobra. El dueño ve el reparto y lo que costaría antes de
apretar "Enviar", y puede elegir mandarla solo por web.
"""
import uuid
from datetime import datetime, time

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.message import Message
from app.models.user import User
from app.services.availability_service import TZ
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


async def rang_today(db: AsyncSession, contact_ids) -> set[uuid.UUID]:
    """Clientes a los que ya les sonó una promo hoy (hora de México). En la web
    no hay riesgo de baneo, así que la promo siempre llega a su chat; lo que se
    limita es la notificación: máximo una al día, para que no las apaguen.
    Solo cuentan las campañas ("[PUSH]"): recordatorios y respuestas del dueño
    siempre suenan."""
    ids = list(contact_ids)
    if not ids:
        return set()
    start = datetime.combine(datetime.now(TZ).date(), time.min, tzinfo=TZ)
    rows = await db.execute(
        select(Message.contact_id).where(
            Message.contact_id.in_(ids),
            Message.campaign_id.is_not(None),
            Message.direction == "outbound",
            Message.content.like("[PUSH]%"),
            Message.created_at >= start,
        )
    )
    return set(rows.scalars().all())


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


def whatsapp_connected(advertiser: User | None) -> bool:
    """Las campañas por WhatsApp salen del número propio del negocio
    (meta_service.send_whatsapp); sin él no sale ninguna. Mismo criterio que
    meta_service._connection, sin descifrar la llave."""
    return bool(
        advertiser
        and advertiser.meta_connection_status == "connected"
        and advertiser.meta_phone_number_id
        and advertiser.meta_token_cipher
        and advertiser.meta_token_iv
        and advertiser.meta_token_tag
    )


def is_web_only(campaign: Campaign) -> bool:
    return bool((campaign.ab_test or {}).get("web_only")) and supports_web(campaign)


async def campaign_reach(db: AsyncSession, campaign: Campaign) -> dict:
    """Cuántos la recibirían gratis por web y cuántos por WhatsApp, igual que
    al enviar. Las reglas anti-baneo (pausa de 48 h, sin actividad…) son de
    WhatsApp: a quien tiene avisos web le llega aunque le hayan mandado algo
    hace poco; `web_silent` son los que la reciben sin sonar (ya les sonó una
    promo hoy).

    Sin WhatsApp conectado no se cuenta a nadie por WhatsApp (no les saldría
    nada): `whatsapp_unreachable` dice a cuántos les llegaría si conecta el
    número de su chip."""
    from app.workers.task_helpers.campaign_ops import _is_contact_active

    contacts = (await db.execute(recipients_query(campaign))).scalars().all()
    web_ok = supports_web(campaign)
    with_push = await contacts_with_push(db, [c.id for c in contacts]) if web_ok else set()
    web = sum(1 for c in contacts if c.id in with_push)
    whatsapp = sum(1 for c in contacts if c.id not in with_push and _is_contact_active(c)[0])
    web_silent = len(await rang_today(db, with_push)) if with_push else 0
    connected = whatsapp_connected(await db.get(User, campaign.advertiser_id))
    unreachable = 0 if connected else whatsapp
    if not connected:
        whatsapp = 0
    return {
        "total": web + whatsapp,
        "web": web,
        "web_silent": web_silent,
        "whatsapp": whatsapp,
        "whatsapp_cost_mxn": round(whatsapp * META_MARKETING_USD_MX * USD_TO_MXN, 2),
        "web_supported": web_ok,
        "whatsapp_connected": connected,
        "whatsapp_unreachable": unreachable,
    }
