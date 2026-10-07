"""Recomiéndalo a un amigo: el amigo se registra con el link (?r=) y quien lo
recomendó gana un sello — una vez por amigo, nunca a sí mismo, no entre
negocios, con tope al mes, y el código no se puede falsificar."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.api.v1.join import join_code, join_verify
from app.database import AsyncSessionLocal
from app.models.contact import Contact
from app.models.loyalty_stamp import LoyaltyStamp
from app.services import referral_service as rs
from tests.test_customer_account import MemRedis
from tests.test_join import (  # noqa: F401  (_on: fixture autouse)
    _cleanup,
    _on,
    _request,
    _seed,
)


async def _join_with_ref(slug, name, phone, redis, ref):
    send = AsyncMock(return_value=True)
    with patch("app.api.v1.join.send_code", send):
        async with AsyncSessionLocal() as db:
            await join_code(request=_request(), slug=slug, body={"name": name, "phone": phone}, db=db, redis=redis)
    code = send.await_args.args[1]
    async with AsyncSessionLocal() as db:
        return await join_verify(request=_request(), slug=slug,
                                 body={"name": name, "phone": phone, "code": code, "ref": ref}, db=db, redis=redis)


async def _referrer(user_id, phone="+525511110001"):
    async with AsyncSessionLocal() as db:
        c = Contact(advertiser_id=user_id, name="Ana López", phone=phone, source="qr")
        db.add(c)
        await db.commit()
        return c.id


async def _referral_stamps(contact_id):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(LoyaltyStamp).where(
            LoyaltyStamp.contact_id == contact_id, LoyaltyStamp.source == "referral"))).scalars().all()


def test_code_round_trips_and_cannot_be_forged():
    cid = uuid.uuid4()
    code = rs.make_ref_code(cid)
    assert rs.parse_ref_code(code) == cid
    tampered = code[:-2] + ("AA" if code[-2:] != "AA" else "BB")
    assert rs.parse_ref_code(tampered) is None
    assert rs.parse_ref_code("basura") is None and rs.parse_ref_code(None) is None


@pytest.mark.asyncio
async def test_friend_who_joins_with_the_link_gives_a_stamp_once():
    uid, slug = await _seed()
    redis = MemRedis()
    try:
        ana = await _referrer(uid)
        code = rs.make_ref_code(ana)
        with patch("app.services.web_push.push_to_contact", AsyncMock(return_value=0)):
            await _join_with_ref(slug, "Beto", "5522220002", redis, code)
            # El mismo amigo otra vez (ya es cliente): nada nuevo. (Otra sesión de
            # Redis: el mismo número solo puede pedir un código por minuto.)
            await _join_with_ref(slug, "Beto", "5522220002", MemRedis(), code)
        stamps = await _referral_stamps(ana)
        assert len(stamps) == 1
    finally:
        await _cleanup(uid)


@pytest.mark.asyncio
async def test_no_stamp_for_yourself_or_for_another_business():
    uid, _slug = await _seed()
    other_uid, other_slug = await _seed()
    redis = MemRedis()
    try:
        ana = await _referrer(uid, phone="+525533330003")
        code = rs.make_ref_code(ana)
        # Ana se registra en OTRO negocio con su propio link: no cuenta.
        await _join_with_ref(other_slug, "Carla", "5544440004", redis, code)
        assert await _referral_stamps(ana) == []
        # Y un amigo "nuevo" con el mismo número de Ana (otro formato) tampoco.
        async with AsyncSessionLocal() as db:
            from app.models.user import User

            user = await db.get(User, uid)
            fake = Contact(id=uuid.uuid4(), advertiser_id=uid, name="Ana", phone="5533330003")
            assert await rs.reward_referral(db, user, code, fake) is False
    finally:
        await _cleanup(uid)
        await _cleanup(other_uid)


@pytest.mark.asyncio
async def test_monthly_cap():
    uid, slug = await _seed()
    redis = MemRedis()
    try:
        ana = await _referrer(uid, phone="+525555550005")
        code = rs.make_ref_code(ana)
        with patch("app.services.web_push.push_to_contact", AsyncMock(return_value=0)):
            for i in range(rs.MAX_REFERRAL_STAMPS_30D + 2):
                await _join_with_ref(slug, f"Amigo{i}", f"55666600{i:02d}", redis, code)
        assert len(await _referral_stamps(ana)) == rs.MAX_REFERRAL_STAMPS_30D
    finally:
        await _cleanup(uid)
