"""Alta de un negocio desde el chat de IaRadio (owner_signup.py,
owner_whatsapp_auth.py, onboarding.py) — real-DB: sin código no hay cuenta;
con código queda el negocio con su página, productos, horario y prueba de
15 días, y la sesión abierta; el mismo WhatsApp después solo entra."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from starlette.requests import Request
from starlette.responses import Response

from app.api.v1.onboarding import TryBody, listen, try_assistant
from app.api.v1.owner_whatsapp_auth import request_code, signup, verify
from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.product import Product
from app.models.user import User
from app.services.owner_signup import WA_EMAIL_DOMAIN, slugify, unique_slug
from tests.test_customer_account import MemRedis as _MemRedis


class MemRedis(_MemRedis):
    async def setex(self, k, ttl, v):  # issue_session guarda el refresh token
        return await self.set(k, v, ex=ttl)

PROFILE = {
    "business_name": "Tacos El Güero",
    "business_category": "Taquería",
    "city": "Tlaxiaco",
    "business_hours": {"mon": ["09:00", "20:00"], "sat": ["09:00", "20:00"]},
    "services": [{"name": "Orden de pastor", "price": 85}, {"name": "Quesadilla", "price": 45}],
}


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-for-signup")
    monkeypatch.setattr(settings, "CUSTOMER_ACCOUNT_ENABLED", True)


def _request(path="/api/v1/auth/whatsapp/x") -> Request:
    return Request({"type": "http", "method": "POST", "path": path, "headers": [],
                    "client": (f"test-{uuid.uuid4()}", 1), "query_string": b""})


def _phone() -> str:
    return "55" + str(uuid.uuid4().int)[:8]


async def _code(phone, redis) -> str:
    send = AsyncMock(return_value=True)
    with patch("app.api.v1.owner_whatsapp_auth.send_code", send):
        await request_code(request=_request(), body={"phone": phone}, redis=redis)
    return send.await_args.args[1]


async def _cleanup(phone):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User.id).where(User.phone == f"+52{phone}"))).scalars().all()
        if users:
            await db.execute(delete(Product).where(Product.advertiser_id.in_(users)))
            await db.execute(delete(User).where(User.id.in_(users)))
        await db.commit()
    await engine.dispose()


class TestSlug:
    def test_slugify(self):
        assert slugify("Tacos El Güero") == "tacos-el-guero"
        assert slugify("¡¡!!") == "mi-negocio"
        assert len(slugify("x" * 200)) <= 44

    @pytest.mark.asyncio
    async def test_unique_slug_adds_number(self):
        await engine.dispose()
        base = f"slug-{uuid.uuid4().hex[:6]}"
        async with AsyncSessionLocal() as db:
            db.add(User(email=f"{uuid.uuid4()}@test.com", password_hash="x", slug=base))
            await db.commit()
            try:
                assert await unique_slug(db, base) == f"{base}-2"
            finally:
                await db.execute(delete(User).where(User.slug == base))
                await db.commit()


class TestSignup:
    @pytest.mark.asyncio
    async def test_wrong_code_creates_nothing(self):
        phone, redis = _phone(), MemRedis()
        try:
            await _code(phone, redis)
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as e:
                    await signup(request=_request(), response=Response(), db=db, redis=redis,
                                 body={"phone": phone, "code": "000000", "name": "Tacos", "profile": PROFILE})
            assert e.value.status_code == 400
            async with AsyncSessionLocal() as db:
                assert (await db.execute(select(User).where(User.phone == f"+52{phone}"))).first() is None
        finally:
            await _cleanup(phone)

    @pytest.mark.asyncio
    async def test_creates_business_with_page_and_session_then_logs_in(self):
        phone, redis = _phone(), MemRedis()
        try:
            code = await _code(phone, redis)
            response = Response()
            async with AsyncSessionLocal() as db:
                out = await signup(request=_request(), response=response, db=db, redis=redis,
                                   body={"phone": phone, "code": code, "name": "Tacos El Güero",
                                         "profile": PROFILE, "color": "#2f9e44"})
            assert out["created"] is True and out["access_token"] and out["slug"].startswith("tacos-el-guero")
            assert "refresh_token=" in response.headers.get("set-cookie", "")
            async with AsyncSessionLocal() as db:
                user = (await db.execute(select(User).where(User.phone == f"+52{phone}"))).scalar_one()
                assert user.email == f"52{phone}@{WA_EMAIL_DOMAIN}" and user.email_verified
                assert user.subscription_status == "trial" and user.plan_expires_at > datetime.now(timezone.utc)
                assert user.business_hours["mon"] == ["09:00", "20:00"] and user.city == "Tlaxiaco"
                assert user.widget_color == "#2f9e44"
                assert "Orden de pastor" in (user.bot_instructions or "")
                prods = (await db.execute(select(Product).where(Product.advertiser_id == user.id))).scalars().all()
                assert sorted(p.name for p in prods) == ["Orden de pastor", "Quesadilla"]

            # Mismo WhatsApp otra vez: entra a su negocio, no crea otro.
            await redis.delete(f"otp_cooldown:52{phone}")
            code = await _code(phone, redis)
            async with AsyncSessionLocal() as db:
                again = await signup(request=_request(), response=Response(), db=db, redis=redis,
                                     body={"phone": phone, "code": code, "name": "Otro nombre", "profile": {}})
            assert again["created"] is False and again["slug"] == out["slug"]

            # Y el login con WhatsApp lo encuentra.
            await redis.delete(f"otp_cooldown:52{phone}")
            code = await _code(phone, redis)
            async with AsyncSessionLocal() as db:
                login = await verify(request=_request(), response=Response(), db=db, redis=redis,
                                     body={"phone": phone, "code": code})
            assert login["access_token"] and login["slug"] == out["slug"]
        finally:
            await _cleanup(phone)

    @pytest.mark.asyncio
    async def test_login_with_unknown_number_says_so(self):
        phone, redis = _phone(), MemRedis()
        code = await _code(phone, redis)
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as e:
                await verify(request=_request(), response=Response(), db=db, redis=redis,
                             body={"phone": phone, "code": code})
        assert e.value.status_code == 404


class TestOnboardingPublic:
    @pytest.mark.asyncio
    async def test_listen_returns_profile_with_name(self):
        from app.services.voice_setup import sanitize_profile

        with patch("app.api.v1.onboarding.extract_profile", AsyncMock(return_value=sanitize_profile(PROFILE))):
            out = await listen(request=_request("/api/v1/public/onboarding/listen"), audio=None,
                               text="Soy Tacos El Güero, vendo tacos en Tlaxiaco", draft=None)
        assert out["profile"]["business_name"] == "Tacos El Güero"
        assert out["profile"]["services"][0]["price"] == 85

    @pytest.mark.asyncio
    async def test_try_uses_the_draft_as_instructions(self):
        gen = AsyncMock(return_value="La orden de pastor cuesta $85 😊")
        with patch("app.services.claude_service.generate_bot_response", gen):
            out = await try_assistant(request=_request("/api/v1/public/onboarding/try"),
                                      body=TryBody(name="Tacos El Güero", profile=PROFILE, question="¿Cuánto el pastor?"))
        assert "$85" in out["answer"]
        kwargs = gen.await_args.kwargs
        assert kwargs["business_name"] == "Tacos El Güero" and "Orden de pastor" in kwargs["bot_instructions"]


class TestNoInbox:
    @pytest.mark.asyncio
    async def test_never_emails_whatsapp_only_accounts(self, monkeypatch):
        from app.core import email

        monkeypatch.setattr(email.settings, "RESEND_API_KEY", "re_test")
        post = AsyncMock()
        with patch("httpx.AsyncClient.post", post):
            assert await email.send_email(f"5255@{WA_EMAIL_DOMAIN}", "Tu prueba termina", "<p>x</p>") is False
        post.assert_not_called()
