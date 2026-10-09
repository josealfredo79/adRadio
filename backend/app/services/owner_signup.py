"""Alta de un negocio desde el chat de IaRadio, sin correo ni contraseña.

El dueño le cuenta su negocio a radiecito (por voz o con botones), ve su
página armarse en una tarjeta dentro de la plática y la publica confirmando
su WhatsApp con un código. Su WhatsApp es su acceso: para volver a entrar
pide otro código (ver api/v1/owner_whatsapp_auth.py).

Lo que se crea es lo mismo que deja el registro normal + "Cuéntale a tu
bot": cuenta en prueba gratis, instrucciones del bot, horario, giro, ciudad,
productos con precio y su link /sitio/{slug} — que en el registro normal el
dueño tenía que elegir a mano y casi nadie lo hacía.
"""
import logging
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import NO_INBOX_DOMAIN
from app.core.plans import TRIAL_DAYS
from app.core.security import generate_referral_code, hash_password
from app.models.product import Product
from app.models.user import User
from app.services.voice_setup import render_instructions, sanitize_profile

logger = logging.getLogger(__name__)

# Correo interno (no se le escribe a nadie, ver core/email.py): User.email es obligatorio y único.
WA_EMAIL_DOMAIN = NO_INBOX_DOMAIN
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,48}[a-z0-9])?$")


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:44].strip("-")
    return text if len(text) >= 2 else "mi-negocio"


async def unique_slug(db: AsyncSession, name: str) -> str:
    base = slugify(name)
    for n in range(1, 50):
        candidate = base if n == 1 else f"{base}-{n}"
        if not (await db.execute(select(User.id).where(User.slug == candidate))).first():
            return candidate
    return f"{base}-{secrets.token_hex(3)}"


async def owner_by_phone(db: AsyncSession, phone: str) -> User | None:
    """phone: canónico sin '+' (customer_account.canonical_phone)."""
    variants = {f"+{phone}", phone}
    return (await db.execute(
        select(User).where((User.phone.in_(variants)) | (User.whatsapp_number.in_(variants))).limit(1)
    )).scalars().first()


async def create_owner(db: AsyncSession, *, phone: str, name: str, profile: dict, color: str | None = None) -> User:
    p = sanitize_profile(profile)
    now = datetime.now(timezone.utc)
    user = User(
        email=f"{phone}@{WA_EMAIL_DOMAIN}",
        # Sin contraseña: entra con código por WhatsApp. Un hash al azar
        # que nadie conoce deja el login por correo cerrado.
        password_hash=hash_password(secrets.token_urlsafe(32)),
        email_verified=True,
        business_name=name,
        business_category=p["business_category"],
        city=p["city"],
        phone=f"+{phone}",
        bot_instructions=render_instructions(p) or None,
        business_hours=p["business_hours"],
        messages_remaining=50,
        plan_expires_at=now + timedelta(days=TRIAL_DAYS),
        last_seen_at=now,
    )
    if color and _HEX.match(color):
        user.widget_color = color
    user.slug = await unique_slug(db, name)
    for _attempt in range(5):
        user.referral_code = generate_referral_code()
        db.add(user)
        try:
            await db.flush()
            break
        except IntegrityError:
            # Choque de referral_code o de slug (dos altas a la vez con el mismo nombre).
            await db.rollback()
            user.slug = f"{slugify(name)}-{secrets.token_hex(2)}"
    else:
        raise RuntimeError("No se pudo crear la cuenta")
    for s in p["services"]:
        db.add(Product(
            advertiser_id=user.id, name=s["name"],
            price=Decimal(str(s["price"])) if s["price"] is not None else None,
            description=s["description"], active=True,
        ))
    await db.commit()
    await db.refresh(user)
    logger.info("[SIGNUP-CHAT] cuenta creada %s slug=%s productos=%s", user.id, user.slug, len(p["services"]))
    return user


async def apply_to_owner(db: AsyncSession, user: User, *, name: str, profile: dict, color: str | None = None) -> User:
    """Lo mismo, para un dueño que YA tiene cuenta (se registró con correo y
    arma su página desde el panel): actualiza su negocio, agrega los productos
    que no tenía (o les pone el precio nuevo) y, si no tenía página, le da su
    link /sitio/{slug}. No toca plan, acceso ni nada más de la cuenta."""
    p = sanitize_profile(profile)
    user.business_name = name or user.business_name
    for field in ("business_category", "city", "business_hours"):
        if p[field]:
            setattr(user, field, p[field])
    instructions = render_instructions(p)
    if instructions:
        user.bot_instructions = instructions
    if color and _HEX.match(color):
        user.widget_color = color
    if not user.slug:
        user.slug = await unique_slug(db, user.business_name or "mi-negocio")
    existing = {
        prod.name.strip().lower(): prod
        for prod in (await db.execute(select(Product).where(Product.advertiser_id == user.id))).scalars().all()
    }
    for s in p["services"]:
        price = Decimal(str(s["price"])) if s["price"] is not None else None
        prod = existing.get(s["name"].lower())
        if prod is None:
            db.add(Product(advertiser_id=user.id, name=s["name"], price=price, description=s["description"], active=True))
        elif price is not None:
            prod.price = price
    await db.commit()
    await db.refresh(user)
    logger.info("[SIGNUP-CHAT] página armada desde el panel %s slug=%s", user.id, user.slug)
    return user
