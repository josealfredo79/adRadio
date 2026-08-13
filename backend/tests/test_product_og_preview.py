"""Real-DB tests for the crawler-facing product OG preview built 2026-08-13.

iaradio.online's frontend is a 100%-client-rendered SPA — the dynamic
og:image/og:title react-helmet-async sets on ProductDetailPage never reach
non-JS-executing crawlers (WhatsApp's link-preview bot notably doesn't run
JS), so pasting a product link into WhatsApp would otherwise always show
the generic whole-site preview instead of that specific product's photo.
main.py's serve_spa() intercepts exactly the /sitio/{slug}/producto/{id}
path shape for known crawler User-Agents and calls _render_product_og_html()
to build real per-product HTML instead — these tests cover that function
and the regex/UA matching it depends on."""
import uuid

import pytest
from sqlalchemy import delete

from app.database import AsyncSessionLocal, engine
from app.main import _CRAWLER_UA_RE, _PRODUCT_PAGE_RE, _render_product_og_html
from app.models.product import Product
from app.models.user import User


async def _seed_user_and_product(**product_overrides):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Tacos El Primo", slug="tacos-og")
        db.add(user)
        await db.flush()
        overrides = {"name": "Taco al pastor", "price": 25, "active": True, **product_overrides}
        product = Product(advertiser_id=user.id, **overrides)
        db.add(product)
        await db.commit()
        return user.id, product.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Product).where(Product.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


class TestProductPageRegex:
    @pytest.mark.parametrize("path", [
        "sitio/tacos-el-primo/producto/12345678-1234-1234-1234-123456789012",
    ])
    def test_matches_real_shape(self, path):
        assert _PRODUCT_PAGE_RE.match(path) is not None

    @pytest.mark.parametrize("path", [
        "sitio/tacos-el-primo",
        "sitio/tacos-el-primo/producto",
        "sitio/tacos-el-primo/producto/not-a-uuid",
        "app/appointments",
        "",
    ])
    def test_does_not_match_other_shapes(self, path):
        assert _PRODUCT_PAGE_RE.match(path) is None


class TestCrawlerUserAgentRegex:
    @pytest.mark.parametrize("ua", [
        "facebookexternalhit/1.1",
        "WhatsApp/2.23.20.0",
        "Mozilla/5.0 (compatible; Twitterbot/1.0)",
        "Slackbot-LinkExpanding 1.0",
    ])
    def test_matches_known_crawlers(self, ua):
        assert _CRAWLER_UA_RE.search(ua) is not None

    @pytest.mark.parametrize("ua", [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
        "",
    ])
    def test_does_not_match_real_browsers(self, ua):
        assert _CRAWLER_UA_RE.search(ua) is None


class TestRenderProductOgHtml:
    @pytest.mark.asyncio
    async def test_real_product_renders_name_and_image(self):
        user_id, product_id = await _seed_user_and_product(photo_url="https://x/taco.jpg")
        try:
            out = await _render_product_og_html("tacos-og", str(product_id), "https://www.iaradio.online")
            assert out is not None
            assert "Taco al pastor" in out
            assert "https://x/taco.jpg" in out
            assert 'property="og:type" content="product"' in out
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_missing_photo_falls_back_to_site_og_image(self):
        user_id, product_id = await _seed_user_and_product(photo_url=None)
        try:
            out = await _render_product_og_html("tacos-og", str(product_id), "https://www.iaradio.online")
            assert "https://www.iaradio.online/og-image.png" in out
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_inactive_product_returns_none(self):
        user_id, product_id = await _seed_user_and_product(active=False)
        try:
            out = await _render_product_og_html("tacos-og", str(product_id), "https://www.iaradio.online")
            assert out is None
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_unknown_slug_returns_none(self):
        await engine.dispose()
        assert await _render_product_og_html("no-existe", str(uuid.uuid4()), "https://www.iaradio.online") is None
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_escapes_html_in_product_name(self):
        """A product name with HTML-special characters must not break out
        of the meta tag attributes (basic XSS/markup-injection guard)."""
        user_id, product_id = await _seed_user_and_product(name='Taco <script>alert(1)</script>"')
        try:
            out = await _render_product_og_html("tacos-og", str(product_id), "https://www.iaradio.online")
            assert "<script>" not in out
            assert "&lt;script&gt;" in out
        finally:
            await _cleanup([user_id])
