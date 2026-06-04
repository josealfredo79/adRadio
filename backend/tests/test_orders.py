"""
Tests de integración para orders endpoints.
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
async def test_list_orders_requires_auth():
    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/orders")
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_update_order_state_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.patch("/api/v1/orders/some-id/state", json={"state": "confirmed"})
        assert resp.status_code == 401
