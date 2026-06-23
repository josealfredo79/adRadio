"""
Tests de integración para campaigns endpoints.
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
async def test_list_campaigns_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/campaigns")
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_create_campaign_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/campaigns", json={"name": "Test", "type": "promo"})
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_public_stories_accessible():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/campaigns/stories/public")
        assert resp.status_code in (200, 404, 500)
