"""Recomiéndalo a un amigo: cada cliente tiene un link personal
(/sitio/{slug}?r={código}); si un amigo entra por ahí y se vuelve cliente
(se registra con su número), quien lo recomendó gana un sello en su tarjeta.

El código NO es el link del portal (ese da acceso a la tarjeta del cliente):
es el id del contacto firmado con SECRET_KEY, que solo sirve para atribuir.
Tope de sellos por recomendación al mes para que no se abuse.
"""
import base64
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.contact import Contact
from app.models.loyalty_stamp import LoyaltyStamp
from app.models.user import User
from app.services.customer_account import canonical_phone
from app.services.loyalty_service import add_stamp, loyalty_config

logger = logging.getLogger(__name__)

MAX_REFERRAL_STAMPS_30D = 5
_SIG_BYTES = 6


def _sig(raw: bytes) -> bytes:
    return hmac.new(settings.SECRET_KEY.encode(), b"referral:" + raw, hashlib.sha256).digest()[:_SIG_BYTES]


def make_ref_code(contact_id: uuid.UUID) -> str:
    raw = contact_id.bytes
    return base64.urlsafe_b64encode(raw + _sig(raw)).rstrip(b"=").decode()


def parse_ref_code(code: str | None) -> uuid.UUID | None:
    if not code or not settings.SECRET_KEY or len(code) > 40:
        return None
    try:
        data = base64.urlsafe_b64decode(code + "=" * (-len(code) % 4))
    except Exception:
        return None
    if len(data) != 16 + _SIG_BYTES:
        return None
    raw, sig = data[:16], data[16:]
    if not hmac.compare_digest(sig, _sig(raw)):
        return None
    return uuid.UUID(bytes=raw)


async def reward_referral(db: AsyncSession, advertiser: User, ref_code: str | None, new_contact: Contact) -> bool:
    """Le da el sello a quien recomendó, si aplica. No hace commit (le toca al
    que llama). True si hubo sello nuevo."""
    referrer_id = parse_ref_code(ref_code)
    if referrer_id is None or referrer_id == new_contact.id or loyalty_config(advertiser) is None:
        return False
    referrer = await db.get(Contact, referrer_id)
    if referrer is None or referrer.advertiser_id != advertiser.id or referrer.status == "blocked":
        return False
    if canonical_phone(referrer.phone) == canonical_phone(new_contact.phone):
        return False  # se recomendó a sí mismo
    since = datetime.now(timezone.utc) - timedelta(days=30)
    recent = (await db.execute(
        select(func.count()).select_from(LoyaltyStamp).where(
            LoyaltyStamp.contact_id == referrer.id,
            LoyaltyStamp.source == "referral",
            LoyaltyStamp.created_at >= since,
        )
    )).scalar_one()
    if recent >= MAX_REFERRAL_STAMPS_30D:
        return False
    stamped = await add_stamp(db, advertiser, referrer.id, "referral", str(new_contact.id))
    if stamped:
        try:
            from app.services.portal_service import portal_url
            from app.services.web_push import push_to_contact

            friend = (new_contact.name or "Tu amigo").split()[0]
            await push_to_contact(
                db, referrer.id,
                title=f"¡Ganaste un sello en {advertiser.business_name or 'tu tarjeta'}! 🎉",
                body=f"{friend} se unió gracias a tu recomendación.",
                url=portal_url(referrer.id),
                tag="referral",
            )
        except Exception:
            logger.warning("[REFERRAL] push to referrer failed", exc_info=True)
    return stamped
