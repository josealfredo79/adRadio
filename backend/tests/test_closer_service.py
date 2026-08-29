"""build_closer_offer — arma una oferta con caducidad real (un Coupon
source="closer" que de verdad expira) cuando el anunciante activó el Closer.
DB real, patrón test_public_site_endpoint.py."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.user import User
from app.services.closer_service import build_closer_offer


async def _seed(closer_config=None, business_hours=None):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(
            email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Estética Luz",
            closer_config=closer_config, business_hours=business_hours,
        )
        db.add(user)
        await db.flush()
        contact = Contact(advertiser_id=user.id, phone=f"+52155{uuid.uuid4().hex[:7]}",
                          name="Marcela Díaz", status="active")
        db.add(contact)
        await db.commit()
        return user.id, contact.id


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Coupon).where(Coupon.advertiser_id == user_id))
        await db.execute(delete(Contact).where(Contact.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_disabled_returns_none():
    user_id, contact_id = await _seed(closer_config={"enabled": False})
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            contact = await db.get(Contact, contact_id)
            assert await build_closer_offer(db, user, contact) is None
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_enabled_creates_expiring_closer_coupon():
    user_id, contact_id = await _seed(closer_config={"enabled": True, "hold_hours": 2, "discount_value": 15})
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            contact = await db.get(Contact, contact_id)
            offer = await build_closer_offer(db, user, contact)
            assert offer is not None
            coupon, text = offer
            assert coupon.source == "closer"
            assert coupon.campaign_id is None
            assert coupon.code in text
            delta = coupon.expires_at - datetime.now(timezone.utc)
            assert timedelta(minutes=110) < delta < timedelta(minutes=130)
            await db.commit()

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Coupon).where(Coupon.advertiser_id == user_id)
            )).scalars().all()
            assert len(rows) == 1
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_does_not_reoffer_when_active_offer_exists():
    user_id, contact_id = await _seed(closer_config={"enabled": True})
    try:
        async with AsyncSessionLocal() as db:
            db.add(Coupon(
                advertiser_id=user_id, contact_id=contact_id, source="closer",
                code=f"EXIST{uuid.uuid4().hex[:5].upper()}", description="Apartado",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ))
            await db.commit()

        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            contact = await db.get(Contact, contact_id)
            assert await build_closer_offer(db, user, contact) is None
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_scarcity_line_only_with_business_hours():
    # Sin business_hours → sin frase de cantidad.
    user_id, contact_id = await _seed(closer_config={"enabled": True})
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            contact = await db.get(Contact, contact_id)
            _c, text = await build_closer_offer(db, user, contact)
            assert "lugares" not in text
    finally:
        await _cleanup(user_id)
