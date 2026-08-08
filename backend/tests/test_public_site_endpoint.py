"""Real-DB tests for the AdRadio-hosted public landing page endpoint —
GET /api/v1/public/site/{slug}. Mirrors the security pattern already
covered for widget_preview in test_widget_endpoints.py::TestWidgetPreview."""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import delete
from starlette.requests import Request

from app.api.v1.public_site import get_public_site, get_public_site_products
from app.database import AsyncSessionLocal, engine
from app.models.product import Product
from app.models.user import User


def _request() -> Request:
    scope = {
        "type": "http", "method": "GET", "path": "/api/v1/public/site/x", "headers": [],
        "client": (f"test-{uuid.uuid4()}", 123), "query_string": b"",
    }
    return Request(scope)


async def _seed_user(**overrides):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", **overrides)
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Product).where(Product.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestGetPublicSite:
    @pytest.mark.asyncio
    async def test_unknown_slug_returns_404(self):
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc_info:
                await get_public_site(request=_request(), slug="no-existe", db=db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_null_slug_is_not_reachable(self):
        user_id = await _seed_user(business_name="Sin slug")
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc_info:
                    await get_public_site(request=_request(), slug="", db=db)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_returns_only_public_safe_fields(self):
        user_id = await _seed_user(
            business_name="Tacos El Primo", business_category="restaurante", city="Tlaxiaco",
            slug="tacos-el-primo", bot_name="Sofia",
        )
        try:
            async with AsyncSessionLocal() as db:
                out = await get_public_site(request=_request(), slug="tacos-el-primo", db=db)
            assert out["advertiser_id"] == str(user_id)
            assert out["business_name"] == "Tacos El Primo"
            assert out["business_category"] == "restaurante"
            assert out["city"] == "Tlaxiaco"
            assert out["agent"] == "Sofia"
            # Nothing sensitive (email, tokens, phone) leaks into the public payload.
            assert "email" not in out
            assert "meta_token_cipher" not in out
            assert "phone" not in out
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_tagline_passthrough_and_default(self):
        user_id = await _seed_user(business_name="Con tagline", slug="con-tagline", landing_tagline="El mejor sabor de la ciudad")
        user_id2 = await _seed_user(business_name="Sin tagline", slug="sin-tagline")
        try:
            async with AsyncSessionLocal() as db:
                out = await get_public_site(request=_request(), slug="con-tagline", db=db)
            assert out["tagline"] == "El mejor sabor de la ciudad"
            async with AsyncSessionLocal() as db:
                out2 = await get_public_site(request=_request(), slug="sin-tagline", db=db)
            assert out2["tagline"] == ""
        finally:
            await _cleanup([user_id, user_id2])

    @pytest.mark.asyncio
    async def test_slug_lookup_is_case_insensitive(self):
        user_id = await _seed_user(business_name="Tacos", slug="mi-negocio")
        try:
            async with AsyncSessionLocal() as db:
                out = await get_public_site(request=_request(), slug="MI-NEGOCIO", db=db)
            assert out["business_name"] == "Tacos"
        finally:
            await _cleanup([user_id])


class TestGetPublicSiteProducts:
    @pytest.mark.asyncio
    async def test_unknown_slug_returns_404(self):
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc_info:
                await get_public_site_products(request=_request(), slug="no-existe", db=db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_only_returns_active_products(self):
        user_id = await _seed_user(business_name="Tacos", slug="con-catalogo")
        try:
            async with AsyncSessionLocal() as db:
                db.add(Product(advertiser_id=user_id, name="Taco al pastor", price=25, active=True))
                db.add(Product(advertiser_id=user_id, name="Descontinuado", price=10, active=False))
                await db.commit()

            async with AsyncSessionLocal() as db:
                out = await get_public_site_products(request=_request(), slug="con-catalogo", db=db)
            assert [p["name"] for p in out] == ["Taco al pastor"]
            assert out[0]["price"] == "25.00"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_never_leaks_other_advertisers_products(self):
        user_id = await _seed_user(business_name="A", slug="negocio-a")
        other_id = await _seed_user(business_name="B", slug="negocio-b")
        try:
            async with AsyncSessionLocal() as db:
                db.add(Product(advertiser_id=other_id, name="Ajeno", active=True))
                await db.commit()

            async with AsyncSessionLocal() as db:
                out = await get_public_site_products(request=_request(), slug="negocio-a", db=db)
            assert out == []
        finally:
            await _cleanup([user_id, other_id])
