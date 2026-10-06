"""Cuenta del cliente /mi (customer_account.py) — número canónico, token,
código de un solo uso con límites, y la lista de sus negocios (real-DB)."""
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete
from starlette.requests import Request

from app.api.v1.customer_account import my_businesses, request_code, verify_code
from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.user import User
from app.services import customer_account as ca


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-for-accounts")
    monkeypatch.setattr(settings, "CUSTOMER_ACCOUNT_ENABLED", True)


class MemRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = str(v)
        return True

    async def get(self, k):
        return self.store.get(k)

    async def incr(self, k):
        self.store[k] = str(int(self.store.get(k, "0")) + 1)
        return int(self.store[k])

    async def expire(self, k, ttl):
        return True

    async def delete(self, k):
        self.store.pop(k, None)


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/public/me/x", "headers": [],
                    "client": (f"test-{uuid.uuid4()}", 1), "query_string": b""})


class TestCanonicalPhone:
    @pytest.mark.parametrize("raw", ["55 1234 5678", "+52 55 1234 5678", "5215512345678", "+521 55 1234 5678",
                                     "(55) 1234-5678"])
    def test_mexican_variants_are_one_number(self, raw):
        assert ca.canonical_phone(raw) == "525512345678"

    @pytest.mark.parametrize("raw", ["", "123", "abc", "1" * 20])
    def test_garbage(self, raw):
        assert ca.canonical_phone(raw) is None

    def test_other_country_keeps_its_code(self):
        assert ca.canonical_phone("+1 555 123 4567") == "15551234567"


class TestToken:
    def test_round_trip(self):
        assert ca.read_account_token(ca.make_account_token("525512345678")) == "525512345678"

    def test_tampered_or_expired_or_other_secret(self, monkeypatch):
        token = ca.make_account_token("525512345678")
        sig = token.split(".")[1]
        other = ca.make_account_token("525599999999").split(".")[0]
        assert ca.read_account_token(f"{other}.{sig}") is None
        assert ca.read_account_token("basura") is None
        assert ca.read_account_token(token, now=time.time() + ca.TOKEN_TTL_SECONDS + 10) is None
        monkeypatch.setattr(settings, "SECRET_KEY", "otra")
        assert ca.read_account_token(token) is None


class TestCode:
    @pytest.mark.asyncio
    async def test_single_use(self):
        r = MemRedis()
        code = await ca.issue_code(r, "525512345678")
        assert len(code) == 6 and code.isdigit()
        assert await ca.check_code(r, "525512345678", "000000" if code != "000000" else "111111") is False
        assert await ca.check_code(r, "525512345678", code) is True
        assert await ca.check_code(r, "525512345678", code) is False

    @pytest.mark.asyncio
    async def test_too_many_wrong_tries_kill_the_code(self):
        r = MemRedis()
        code = await ca.issue_code(r, "525512345678")
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(ca.CODE_MAX_ATTEMPTS):
            await ca.check_code(r, "525512345678", wrong)
        assert await ca.check_code(r, "525512345678", code) is False

    @pytest.mark.asyncio
    async def test_resend_cooldown_and_daily_cap(self):
        r = MemRedis()
        await ca.issue_code(r, "525512345678")
        with pytest.raises(ca.CodeError):
            await ca.issue_code(r, "525512345678")
        for _ in range(ca.CODE_DAILY_MAX - 1):
            r.store.pop("otp_cooldown:525512345678")
            await ca.issue_code(r, "525512345678")
        r.store.pop("otp_cooldown:525512345678")
        with pytest.raises(ca.CodeError):
            await ca.issue_code(r, "525512345678")


async def _seed():
    """Ana es clienta de dos negocios (guardada con formatos distintos); en
    el segundo además tiene cita y cupón. Beto es de otro número."""
    await engine.dispose()
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        a = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Barbería Don Pepe")
        b = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Tacos El Primo",
                 loyalty_config={"enabled": True, "stamps_required": 5, "reward": "Orden gratis"})
        db.add_all([a, b])
        await db.flush()
        tail = f"{uuid.uuid4().int % 10**8:08d}"
        ana_a = Contact(advertiser_id=a.id, name="Ana", phone=f"+52155{tail}")
        ana_b = Contact(advertiser_id=b.id, name="Ana L.", phone=f"55{tail}")
        beto = Contact(advertiser_id=a.id, name="Beto", phone=f"+52133{tail}")
        db.add_all([ana_a, ana_b, beto])
        await db.flush()
        db.add(Appointment(advertiser_id=b.id, contact_id=ana_b.id, customer_name="Ana", service="Mesa para 4",
                           scheduled_at=now + timedelta(days=1), status="confirmed"))
        db.add(Coupon(advertiser_id=b.id, contact_id=ana_b.id, code=f"T{tail}", discount_value=10,
                      expires_at=now + timedelta(days=3)))
        await db.commit()
        return [a.id, b.id], f"52155{tail}", f"55 {tail[:4]} {tail[4:]}", beto.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for uid in user_ids:
            await db.execute(delete(Coupon).where(Coupon.advertiser_id == uid))
            await db.execute(delete(Message).where(Message.advertiser_id == uid))
            await db.execute(delete(Appointment).where(Appointment.advertiser_id == uid))
            await db.execute(delete(Contact).where(Contact.advertiser_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()
    await engine.dispose()


class TestEndpoints:
    @pytest.mark.asyncio
    async def test_full_login_lists_all_my_businesses(self):
        user_ids, stored_phone, typed_phone, _ = await _seed()
        r = MemRedis()
        try:
            send = AsyncMock(return_value=True)
            with patch("app.api.v1.customer_account.send_code", send):
                async with AsyncSessionLocal() as db:
                    await request_code(request=_request(), body={"phone": typed_phone}, db=db, redis=r)
            phone, code = send.await_args.args
            assert phone == ca.canonical_phone(stored_phone)

            out = await verify_code(request=_request(), body={"phone": typed_phone, "code": code}, redis=r)
            async with AsyncSessionLocal() as db:
                data = await my_businesses(request=_request(), authorization=f"Bearer {out['token']}", db=db)
            names = [x["name"] for x in data["businesses"]]
            assert names == ["Barbería Don Pepe", "Tacos El Primo"]
            tacos = data["businesses"][1]
            assert tacos["next_appointment"]["service"] == "Mesa para 4" and tacos["coupons"] == 1
            assert tacos["loyalty"]["required"] == 5 and tacos["portal_path"].startswith("/c/")
            assert data["businesses"][0]["loyalty"] is None
        finally:
            await _cleanup(user_ids)

    @pytest.mark.asyncio
    async def test_chat_list_shows_last_message_newest_first(self):
        # /mi es una lista de chats como WhatsApp: último mensaje y el más reciente arriba.
        from sqlalchemy import select

        user_ids, stored_phone, _, _ = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                ana_b = (await db.execute(select(Contact).where(Contact.advertiser_id == user_ids[1]))).scalar_one()
                db.add_all([
                    Message(advertiser_id=user_ids[1], contact_id=ana_b.id, direction="inbound",
                            content="¿tienen mesa?", status="received",
                            created_at=datetime.now(timezone.utc) - timedelta(minutes=5)),
                    Message(advertiser_id=user_ids[1], contact_id=ana_b.id, direction="outbound",
                            content="[PENDING:audio] {}", status="queued"),
                    Message(advertiser_id=user_ids[1], contact_id=ana_b.id, direction="outbound",
                            content="Sí, a las 8 te esperamos", status="sent"),
                ])
                await db.commit()
                data = await my_businesses(request=_request(), authorization=f"Bearer {ca.make_account_token(ca.canonical_phone(stored_phone))}", db=db)
            first = data["businesses"][0]
            assert first["name"] == "Tacos El Primo"
            assert first["last_message"]["text"] == "Sí, a las 8 te esperamos" and first["last_message"]["from_me"] is False
            assert data["businesses"][1]["last_message"] is None
        finally:
            await _cleanup(user_ids)

    @pytest.mark.asyncio
    async def test_unknown_number_gets_the_same_answer_and_no_whatsapp(self):
        r = MemRedis()
        send = AsyncMock(return_value=True)
        with patch("app.api.v1.customer_account.send_code", send):
            async with AsyncSessionLocal() as db:
                out = await request_code(request=_request(), body={"phone": "55 0000 0001"}, db=db, redis=r)
        assert out["message"] == "Si tu número está registrado con algún negocio, te llegará un código por WhatsApp."
        send.assert_not_called()

    @pytest.mark.asyncio
    async def test_wrong_code_and_bad_token(self):
        r = MemRedis()
        with pytest.raises(HTTPException) as exc:
            await verify_code(request=_request(), body={"phone": "5512345678", "code": "123456"}, redis=r)
        assert exc.value.status_code == 400
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc:
                await my_businesses(request=_request(), authorization="Bearer nope", db=db)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_blocked_contact_is_hidden(self):
        user_ids, stored_phone, _, _ = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                c = (await db.execute(
                    Contact.__table__.select().where(Contact.advertiser_id == user_ids[0], Contact.name == "Ana")
                )).first()
                (await db.get(Contact, c.id)).status = "blocked"
                await db.commit()
            token = ca.make_account_token(ca.canonical_phone(stored_phone))
            async with AsyncSessionLocal() as db:
                data = await my_businesses(request=_request(), authorization=f"Bearer {token}", db=db)
            assert [x["name"] for x in data["businesses"]] == ["Tacos El Primo"]
        finally:
            await _cleanup(user_ids)


class TestSwitchedOff:
    @pytest.mark.asyncio
    async def test_no_codes_until_it_is_turned_on(self, monkeypatch):
        monkeypatch.setattr(settings, "CUSTOMER_ACCOUNT_ENABLED", False)
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc:
                await request_code(request=_request(), body={"phone": "5512345678"}, db=db, redis=MemRedis())
        assert exc.value.status_code == 503


class TestSendCode:
    @pytest.mark.asyncio
    async def test_uses_the_authentication_template_with_copy_button(self, monkeypatch):
        monkeypatch.setattr(settings, "IARADIO_WA_PHONE_NUMBER_ID", "123")
        monkeypatch.setattr(settings, "IARADIO_WA_TOKEN", "tok")
        graph = AsyncMock(return_value={"messages": [{"id": "wamid.1"}]})
        with patch("app.services.meta_client.graph_request", graph):
            assert await ca.send_code("525512345678", "482913") is True
        body = graph.await_args.kwargs["body"]
        assert body["to"] == "525512345678"
        assert body["template"]["name"] == "codigo_acceso"
        assert body["template"]["components"][1]["parameters"][0]["text"] == "482913"

    @pytest.mark.asyncio
    async def test_without_central_number_it_does_not_send(self, monkeypatch):
        monkeypatch.setattr(settings, "IARADIO_WA_PHONE_NUMBER_ID", "")
        assert await ca.send_code("525512345678", "482913") is False


class TestDiscover:
    async def _seed(self):
        await engine.dispose()
        tag = uuid.uuid4().hex[:6]
        async with AsyncSessionLocal() as db:
            def biz(name, city, **kw):
                return User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name=f"{name} {tag}",
                            city=city, slug=kw.pop("slug", f"{name.lower().replace(' ', '-')}-{tag}"), **kw)

            mine = biz("Barberia Pepe", "Tlaxiaco")
            near = biz("Tacos Primo", "Tlaxiaco", loyalty_config={"enabled": True, "stamps_required": 5, "reward": "Orden gratis"})
            far = biz("Estetica Lupita", "Oaxaca")
            hidden = biz("Oculto", "Tlaxiaco", directory_listed=False)
            gone = biz("Cerrado", "Tlaxiaco", subscription_status="churned")
            noslug = biz("Sinlink", "Tlaxiaco", slug=None)
            users = [mine, near, far, hidden, gone, noslug]
            db.add_all(users)
            await db.flush()
            tail = f"{uuid.uuid4().int % 10**8:08d}"
            db.add(Contact(advertiser_id=mine.id, name="Ana López", phone=f"+52155{tail}"))
            await db.commit()
            return [u.id for u in users], tag, ca.make_account_token(f"5255{tail}"), near, hidden

    @pytest.mark.asyncio
    async def test_lists_other_listed_businesses_nearby_first(self):
        ids, tag, token, *_ = await self._seed()
        try:
            from app.api.v1.customer_account import discover

            async with AsyncSessionLocal() as db:
                out = await discover(request=_request(), q=tag, authorization=f"Bearer {token}", db=db)
            names = [b["name"].removesuffix(f" {tag}") for b in out["businesses"]]
            assert names == ["Tacos Primo", "Estetica Lupita"]
            assert out["businesses"][0]["reward"] == "Orden gratis"
            async with AsyncSessionLocal() as db:
                out = await discover(request=_request(), q="Oaxaca", authorization=f"Bearer {token}", db=db)
            assert any(b["name"] == f"Estetica Lupita {tag}" for b in out["businesses"])
        finally:
            await _cleanup(ids)

    @pytest.mark.asyncio
    async def test_connect_creates_one_contact_with_the_verified_number(self):
        ids, _, token, near, hidden = await self._seed()
        try:
            from app.api.v1.customer_account import connect

            for _ in range(2):
                async with AsyncSessionLocal() as db:
                    out = await connect(request=_request(), body={"slug": near.slug}, authorization=f"Bearer {token}", db=db)
            async with AsyncSessionLocal() as db:
                rows = (await db.execute(
                    Contact.__table__.select().where(Contact.advertiser_id == near.id)
                )).all()
            assert len(rows) == 1
            c = rows[0]
            assert (c.name, c.source, c.consent_status) == ("Ana López", "directory", "confirmed")
            assert c.phone == "+" + ca.read_account_token(token)
            assert out["portal_path"].startswith("/c/")

            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc:
                    await connect(request=_request(), body={"slug": hidden.slug}, authorization=f"Bearer {token}", db=db)
            assert exc.value.status_code == 404
        finally:
            await _cleanup(ids)

    @pytest.mark.asyncio
    async def test_blocked_by_that_business_cannot_rejoin(self):
        ids, _, token, near, _ = await self._seed()
        try:
            from app.api.v1.customer_account import connect

            async with AsyncSessionLocal() as db:
                db.add(Contact(advertiser_id=near.id, name="Ana", phone="+" + ca.read_account_token(token), status="blocked"))
                await db.commit()
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc:
                    await connect(request=_request(), body={"slug": near.slug}, authorization=f"Bearer {token}", db=db)
            assert exc.value.status_code == 403
        finally:
            await _cleanup(ids)
