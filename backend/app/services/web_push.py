"""Notificaciones web (Web Push) a los clientes que las aceptaron en su
portal — el canal gratis que reemplaza a WhatsApp (cobrado por Meta) en
recordatorios de cita y campañas, para quien lo tenga activado.

Entrega "best effort": que el servicio de push acepte el aviso (201) no
garantiza que el cliente lo vea, igual que un WhatsApp entregado no garantiza
que lo lea. Por eso quien llama decide: si ningún navegador del cliente lo
aceptó, se cae a WhatsApp como siempre.

Generar llaves:  python -m app.services.web_push --generate
"""
import asyncio
import base64
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.push_subscription import PushSubscription

logger = logging.getLogger(__name__)

# El servicio de push guarda el aviso hasta que el celular se conecte. Un
# recordatorio de cita o una promo de hace 2 días ya no sirve.
DEFAULT_TTL_SECONDS = 24 * 3600
# Tras varios fallos que no son 404/410 (ej. 5xx del servicio), dejamos de
# intentar con ese navegador; el cliente la reactiva desde su portal.
MAX_FAILURES = 5


def push_enabled() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def generate_vapid_keys() -> tuple[str, str]:
    """(public, private) en base64url: la pública en el formato que espera el
    navegador (applicationServerKey, punto sin comprimir) y la privada como
    los 32 bytes crudos que acepta pywebpush."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    raw_private = key.private_numbers().private_value.to_bytes(32, "big")
    raw_public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return b64(raw_public), b64(raw_private)


def _send_one(sub: PushSubscription, payload: str, ttl: int) -> int:
    """Síncrono (pywebpush usa requests) — se llama en un hilo. Regresa el
    código HTTP del servicio de push; 0 si ni siquiera hubo respuesta."""
    from pywebpush import WebPushException, webpush

    try:
        resp = webpush(
            subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            # pywebpush muta este dict (aud/exp) — uno nuevo en cada envío.
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            ttl=ttl,
            timeout=10,
        )
        return getattr(resp, "status_code", 201)
    except WebPushException as e:
        status = getattr(e.response, "status_code", 0) if e.response is not None else 0
        logger.info("[PUSH] endpoint rejected (%s): %s", status, str(e)[:120])
        return status
    except Exception:
        logger.exception("[PUSH] send failed")
        return 0


async def contacts_with_push(db: AsyncSession, contact_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """De estos contactos, cuáles tienen al menos un navegador suscrito — para
    rutear una campaña completa con una sola consulta."""
    if not push_enabled() or not contact_ids:
        return set()
    rows = await db.execute(
        select(PushSubscription.contact_id).where(
            PushSubscription.contact_id.in_(contact_ids),
            PushSubscription.failure_count < MAX_FAILURES,
        )
    )
    return set(rows.scalars().all())


async def push_to_contact(
    db: AsyncSession,
    contact_id: uuid.UUID,
    *,
    title: str,
    body: str,
    url: str,
    image: str | None = None,
    tag: str | None = None,
    ttl: int = DEFAULT_TTL_SECONDS,
) -> int:
    """Manda el aviso a todos los navegadores del contacto. Regresa cuántos lo
    aceptaron (0 = el que llama debe caer a WhatsApp). Borra las
    suscripciones muertas. No hace commit — eso le toca al que llama."""
    if not push_enabled():
        return 0
    subs = (
        await db.execute(
            select(PushSubscription).where(
                PushSubscription.contact_id == contact_id,
                PushSubscription.failure_count < MAX_FAILURES,
            )
        )
    ).scalars().all()
    if not subs:
        return 0

    payload = json.dumps(
        {"title": title, "body": body[:300], "url": url, "image": image or None, "tag": tag or None},
        ensure_ascii=False,
    )
    statuses = await asyncio.gather(*(asyncio.to_thread(_send_one, s, payload, ttl) for s in subs))

    accepted = 0
    dead: list[uuid.UUID] = []
    now = datetime.now(timezone.utc)
    for sub, status in zip(subs, statuses):
        if 200 <= status < 300:
            accepted += 1
            sub.failure_count = 0
            sub.last_success_at = now
        elif status in (404, 410):
            dead.append(sub.id)
        else:
            sub.failure_count = (sub.failure_count or 0) + 1
    if dead:
        await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(dead)))
    return accepted


if __name__ == "__main__":
    import sys

    if "--generate" in sys.argv:
        public, private = generate_vapid_keys()
        print(f"VAPID_PUBLIC_KEY={public}\nVAPID_PRIVATE_KEY={private}")
