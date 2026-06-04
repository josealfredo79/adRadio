"""
Tests de integración para auth endpoints.
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
async def test_register_returns_201():
    from httpx import AsyncClient, ASGITransport
    import uuid
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"test-{uuid.uuid4().hex[:8]}@example.com"
        resp = await client.post("/api/v1/auth/register", json={
            "email": email,
            "password": "TestPass1",
            "business_name": "Test Business",
        })
        assert resp.status_code == 201
        assert "mensaje" in resp.json()


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_register_duplicate_email_returns_409():
    from httpx import AsyncClient, ASGITransport
    import uuid
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
        await client.post("/api/v1/auth/register", json={
            "email": email,
            "password": "TestPass1",
            "business_name": "Test",
        })
        resp = await client.post("/api/v1/auth/register", json={
            "email": email,
            "password": "TestPass1",
            "business_name": "Test",
        })
        assert resp.status_code == 409


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_login_invalid_credentials_returns_401():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/login", json={
            "email": "nonexistent@example.com",
            "password": "WrongPass1",
        })
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_forgot_password_always_returns_200():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/forgot-password", json={
            "email": "nobody@example.com",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "mensaje" in data


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_reset_password_invalid_token_returns_400():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/reset-password", json={
            "token": "invalid-token-123",
            "new_password": "NewPass123",
        })
        assert resp.status_code == 400


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_protected_route_without_token_returns_401():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/campaigns")
        assert resp.status_code == 401
