"""Registro por QR de mostrador (api/v1/join.py) — real-DB: sin código no
hay portal, el cliente nuevo queda con opt-in, el que ya existía recupera SU
tarjeta (no una nueva), y los apagados/bloqueados."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from starlette.requests import Request

from app.api.v1.join import join_code, join_info, join_verify
from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.user import User
from app.services import customer_account as ca
from app.services.portal_service import make_portal_token, read_portal_token
from tests.test_customer_account import MemRedis


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-for-join")
    monkeypatch.setattr(settings, "CUSTOMER_ACCOUNT_ENABLED", True)


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/public/join/x", "headers": [],
                    "client": (f"test-{uuid.uuid4()}", 1), "query_string": b""})


async def _seed():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Barbería Don Pepe",
                    slug=f"pepe-{uuid.uuid4().hex[:8]}",
                    loyalty_config={"enabled": True, "stamps_required": 8, "reward": "Un corte gratis"})
        db.add(user)
        await db.commit()
        return user.id, user.slug


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Contact).where(Contact.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


async def _join(slug, name, phone, redis, code=None):
    send = AsyncMock(return_value=True)
    with patch("app.api.v1.join.send_code", send):
        async with AsyncSessionLocal() as db:
            await join_code(request=_request(), slug=slug, body={"name": name, "phone": phone}, db=db, redis=redis)
    sent_code = send.await_args.args[1]
    async with AsyncSessionLocal() as db:
        return await join_verify(request=_request(), slug=slug,
                                 body={"name": name, "phone": phone, "code": code or sent_code}, db=db, redis=redis)


class TestJoin:
    @pytest.mark.asyncio
    async def test_info_shows_the_business_and_its_reward(self):
        user_id, slug = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                info = await join_info(request=_request(), slug=slug, db=db)
            assert info["available"] is True and info["business"]["name"] == "Barbería Don Pepe"
            assert info["loyalty"] == {"required": 8, "reward": "Un corte gratis"}
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_new_customer_gets_a_contact_with_opt_in_and_a_session(self):
        user_id, slug = await _seed()
        try:
            out = await _join(slug, "  Ana   López ", "55 1234 5678", MemRedis())
            cid = read_portal_token(out["portal_path"].removeprefix("/c/"))
            async with AsyncSessionLocal() as db:
                contact = await db.get(Contact, cid)
            assert (contact.name, contact.phone, contact.source, contact.consent_status) == (
                "Ana López", "+525512345678", "qr", "confirmed")
            assert ca.read_account_token(out["account_token"]) == "525512345678"
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_existing_customer_gets_their_own_card_not_a_new_one(self):
        user_id, slug = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                existing = Contact(advertiser_id=user_id, name="Ana (WhatsApp)", phone="+5215512345678")
                db.add(existing)
                await db.commit()
                existing_id = existing.id
            out = await _join(slug, "Ana", "5512345678", MemRedis())
            assert out["portal_path"] == f"/c/{make_portal_token(existing_id)}"
            async with AsyncSessionLocal() as db:
                rows = (await db.execute(select(Contact).where(Contact.advertiser_id == user_id))).scalars().all()
            assert len(rows) == 1 and rows[0].name == "Ana (WhatsApp)"
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_wrong_code_gives_no_portal(self):
        user_id, slug = await _seed()
        try:
            with pytest.raises(HTTPException) as exc:
                await _join(slug, "Ana", "5512345678", MemRedis(), code="999999x")
            assert exc.value.status_code == 400
            async with AsyncSessionLocal() as db:
                assert (await db.execute(select(Contact).where(Contact.advertiser_id == user_id))).first() is None
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_blocked_customer_is_refused(self):
        user_id, slug = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Contact(advertiser_id=user_id, name="Spam", phone="+525512345678", status="blocked"))
                await db.commit()
            with pytest.raises(HTTPException) as exc:
                await _join(slug, "Spam", "5512345678", MemRedis())
            assert exc.value.status_code == 403
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_switched_off_and_unknown_business(self, monkeypatch):
        user_id, slug = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc:
                    await join_info(request=_request(), slug="no-existe-" + uuid.uuid4().hex, db=db)
                assert exc.value.status_code == 404
            monkeypatch.setattr(settings, "CUSTOMER_ACCOUNT_ENABLED", False)
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc:
                    await join_code(request=_request(), slug=slug, body={"name": "Ana", "phone": "5512345678"},
                                    db=db, redis=MemRedis())
                assert exc.value.status_code == 503
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_business_daily_cap(self, monkeypatch):
        monkeypatch.setattr("app.api.v1.join.BUSINESS_DAILY_CODES", 1)
        user_id, slug = await _seed()
        r = MemRedis()
        try:
            with patch("app.api.v1.join.send_code", AsyncMock(return_value=True)):
                async with AsyncSessionLocal() as db:
                    await join_code(request=_request(), slug=slug, body={"name": "Ana", "phone": "5512345678"}, db=db, redis=r)
                    with pytest.raises(HTTPException) as exc:
                        await join_code(request=_request(), slug=slug, body={"name": "Beto", "phone": "5587654321"},
                                        db=db, redis=r)
            assert exc.value.status_code == 429
        finally:
            await _cleanup(user_id)
