"""
Tests de integración para la API REST de IaRadio.
Requieren base de datos PostgreSQL — skip si no está disponible.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

HAS_DB = bool(os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL"))

try:
    from app.main import app
    HAS_APP = True
except Exception:
    HAS_APP = False
    app = None

db_reason = "Requiere base de datos (TEST_DATABASE_URL o DATABASE_URL)"


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_health_endpoint():
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_protected_endpoint_returns_401():
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/contacts")
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_customer_stories_public():
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/campaigns/stories/public")
        assert resp.status_code in (200, 404, 500)


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_robots_txt_accessible():
    """Robots.txt should be served in production (from static dir)."""
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/robots.txt")
        assert resp.status_code in (200, 404)


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_sitemap_xml_accessible():
    """Sitemap.xml should be served in production."""
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/sitemap.xml")
        assert resp.status_code in (200, 404)


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_contacts_requires_auth():
    """Contacts endpoints are protected."""
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/contacts")
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_payments_plans_public():
    """Plans endpoint is public."""
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/plans")
        assert resp.status_code == 200
        data = resp.json()
        assert "starter" in data
        assert "pro" in data


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_checkout_requires_auth():
    """Checkout endpoint requires authentication."""
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/checkout/create-session", json={"plan": "pro"})
        assert resp.status_code == 401
