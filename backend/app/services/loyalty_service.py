"""Tarjeta de lealtad del portal del cliente (/c/{token}).

Es el regalo con valor que hace que el cliente prefiera la web a WhatsApp:
el dueño define cuántos sellos y qué premio, y los sellos caen solos —
cita marcada como completada, pedido confirmado. El regalo de bienvenida son
dos sellos extra: uno al abrir la tarjeta por primera vez y otro al activar
los avisos web (que es lo que luego ahorra los WhatsApp cobrados).

Nada aquí hace commit: le toca al que llama, igual que web_push.py.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.loyalty_stamp import LoyaltyStamp
from app.models.user import User

logger = logging.getLogger(__name__)

LOYALTY_DEFAULTS = {"enabled": False, "stamps_required": 8, "reward": ""}
# Lo que el cliente ve como motivo de cada sello en su tarjeta.
SOURCE_LABELS = {
    "welcome": "Regalo de bienvenida",
    "push": "Activaste los avisos",
    "appointment": "Cita",
    "order": "Pedido",
    "manual": "Visita",
}


def loyalty_config(advertiser: User) -> dict | None:
    """La config activa del negocio, o None si no tiene tarjeta (apagada o sin
    premio — una tarjeta sin premio no es un regalo)."""
    cfg = {**LOYALTY_DEFAULTS, **(advertiser.loyalty_config or {})}
    if not cfg["enabled"] or not (cfg["reward"] or "").strip():
        return None
    return cfg


async def add_stamp(
    db: AsyncSession, advertiser: User, contact_id: uuid.UUID | None, source: str, source_key: str = ""
) -> bool:
    """True si el sello es nuevo. Repetir el mismo (source, source_key) no hace
    nada, así que se puede llamar sin revisar antes."""
    if contact_id is None or loyalty_config(advertiser) is None:
        return False
    result = await db.execute(
        insert(LoyaltyStamp)
        .values(id=uuid.uuid4(), advertiser_id=advertiser.id, contact_id=contact_id, source=source, source_key=source_key)
        .on_conflict_do_nothing(constraint="uq_loyalty_stamp_source")
    )
    return result.rowcount > 0


async def remove_stamp(db: AsyncSession, contact_id: uuid.UUID | None, source: str, source_key: str) -> None:
    """Deshace el sello de una cita/pedido que dejó de contar (el dueño la
    regresó de "completada" o canceló el pedido). Un sello ya usado en un
    premio entregado se queda: el premio ya salió."""
    if contact_id is None:
        return
    await db.execute(
        delete(LoyaltyStamp).where(
            LoyaltyStamp.contact_id == contact_id,
            LoyaltyStamp.source == source,
            LoyaltyStamp.source_key == source_key,
            LoyaltyStamp.redeemed_at.is_(None),
        )
    )


async def has_unopened_gift(db: AsyncSession, advertiser: User, contact_id: uuid.UUID | None) -> bool:
    """El negocio tiene tarjeta y este cliente todavía no la abre (no tiene el
    sello de bienvenida) — la invitación del bot puede ofrecerle el regalo."""
    if contact_id is None or loyalty_config(advertiser) is None:
        return False
    opened = (
        await db.execute(
            select(LoyaltyStamp.id).where(LoyaltyStamp.contact_id == contact_id, LoyaltyStamp.source == "welcome")
        )
    ).first()
    return opened is None


async def get_card(db: AsyncSession, advertiser: User, contact_id: uuid.UUID) -> dict | None:
    cfg = loyalty_config(advertiser)
    if cfg is None:
        return None
    rows = (
        await db.execute(
            select(LoyaltyStamp.source, LoyaltyStamp.created_at)
            .where(LoyaltyStamp.contact_id == contact_id, LoyaltyStamp.redeemed_at.is_(None))
            .order_by(LoyaltyStamp.created_at.asc())
        )
    ).all()
    required = cfg["stamps_required"]
    return {
        "stamps": len(rows),
        "required": required,
        "reward": cfg["reward"],
        "rewards_ready": len(rows) // required,
        "history": [
            {"label": SOURCE_LABELS.get(source, "Sello"), "at": created_at.isoformat() if created_at else None}
            for source, created_at in rows[-required:]
        ],
    }


class NoRewardReady(Exception):
    pass


async def redeem_reward(db: AsyncSession, advertiser: User, contact_id: uuid.UUID) -> None:
    """El dueño le entregó el premio: los `stamps_required` sellos más viejos
    quedan usados y lo que sobre pasa a la tarjeta nueva."""
    cfg = loyalty_config(advertiser)
    if cfg is None:
        raise NoRewardReady("La tarjeta de lealtad está apagada")
    required = cfg["stamps_required"]
    ids = (
        await db.execute(
            select(LoyaltyStamp.id)
            .where(LoyaltyStamp.contact_id == contact_id, LoyaltyStamp.redeemed_at.is_(None))
            .order_by(LoyaltyStamp.created_at.asc())
            .limit(required)
            .with_for_update()
        )
    ).scalars().all()
    if len(ids) < required:
        raise NoRewardReady("Este cliente todavía no llena su tarjeta")
    now = datetime.now(timezone.utc)
    for stamp in (await db.execute(select(LoyaltyStamp).where(LoyaltyStamp.id.in_(ids)))).scalars():
        stamp.redeemed_at = now


async def stamp_line(db: AsyncSession, advertiser: User, contact_id: uuid.UUID | None) -> str:
    """Línea para el final de una confirmación (mismo mensaje, sin costo
    extra) cuando esa confirmación acaba de sellar."""
    if contact_id is None:
        return ""
    card = await get_card(db, advertiser, contact_id)
    if card is None:
        return ""
    if card["rewards_ready"]:
        return f"\n\n🎁 ¡Llenaste tu tarjeta de cliente! Ya puedes pedir tu premio: {card['reward']}"
    return f"\n\n⭐ ¡Sumaste un sello! Llevas {card['stamps']} de {card['required']} para: {card['reward']}"


async def notify_stamp(db: AsyncSession, advertiser: User, contact_id: uuid.UUID | None) -> None:
    """Aviso web (gratis) de que sumó un sello. Solo push: no vale la pena
    pagarle a Meta un WhatsApp por esto. Nunca lanza; hace commit propio
    porque push_to_contact actualiza las suscripciones."""
    if contact_id is None:
        return
    try:
        card = await get_card(db, advertiser, contact_id)
        if card is None:
            return
        from app.services.portal_service import portal_url
        from app.services.web_push import push_to_contact

        if card["rewards_ready"]:
            title = "🎁 ¡Llenaste tu tarjeta!"
            body = f"Ya puedes pedir tu premio en {advertiser.business_name or 'el negocio'}: {card['reward']}"
        else:
            title = "⭐ ¡Sumaste un sello!"
            body = f"Llevas {card['stamps']} de {card['required']} para: {card['reward']}"
        await push_to_contact(
            db, contact_id, title=title, body=body, url=portal_url(contact_id), tag="loyalty",
        )
        await db.commit()
    except Exception:
        logger.warning("[LOYALTY] stamp notification failed contact=%s", contact_id, exc_info=True)
        await db.rollback()


async def bot_note(db: AsyncSession, advertiser: User, contact_id: uuid.UUID | None) -> str:
    """Lo que el bot necesita saber de la tarjeta para contestar "¿cuántos
    sellos llevo?" o "¿qué gano?". Vacío si el negocio no tiene tarjeta."""
    cfg = loyalty_config(advertiser)
    if cfg is None:
        return ""
    note = (
        f"TARJETA DE LEALTAD: {advertiser.business_name or 'el negocio'} tiene tarjeta de sellos en el "
        f"portal web del cliente. Al juntar {cfg['stamps_required']} sellos gana: {cfg['reward']}. "
        "Se gana un sello por cada cita completada o pedido, y de regalo uno al abrir la tarjeta y otro "
        "al activar los avisos en la web."
    )
    if contact_id is not None:
        card = await get_card(db, advertiser, contact_id)
        if card:
            if card["rewards_ready"]:
                note += f" ESTE CLIENTE ya llenó su tarjeta ({card['stamps']} sellos): puede pedir su premio."
            else:
                note += f" ESTE CLIENTE lleva {card['stamps']} de {card['required']} sellos."
    return note + " Menciónalo solo si el cliente pregunta por sellos, premios o su tarjeta."
