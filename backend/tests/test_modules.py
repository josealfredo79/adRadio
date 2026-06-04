"""
Smoke tests for modules without coverage: widget, profile, templates, automations,
team, knowledge_base, conversations, payments, radio, analytics.
Require DB — skip if not available.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import uuid

HAS_DB = bool(os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL"))

try:
    from app.main import app
    HAS_APP = True
except Exception:
    HAS_APP = False
    app = None

db_reason = "Requiere base de datos (TEST_DATABASE_URL o DATABASE_URL)"

AUTH_EMAIL = f"modtest-{uuid.uuid4().hex[:8]}@example.com"
AUTH_PASS = "TestPass1"

_token = None


async def _register():
    global _token
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/register", json={
            "email": AUTH_EMAIL,
            "password": AUTH_PASS,
            "business_name": "Module Test",
        })
        if r.status_code == 201:
            _token = r.json().get("token")
        if not _token:
            r2 = await c.post("/api/v1/auth/login", json={
                "email": AUTH_EMAIL,
                "password": AUTH_PASS,
            })
            if r2.status_code == 200:
                _token = r2.json().get("access_token")


def _headers():
    return {"Authorization": f"Bearer {_token}"} if _token else {}


# ── Widget ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_widget_get_snippet_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/widget/snippet")
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_widget_preview_public():
    """Public endpoint should 404 for random UUID (but not 401)."""
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(f"/api/v1/widget/preview/{uuid.uuid4()}")
        assert resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_widget_get_config_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/widget/config")
        assert resp.status_code == 401


# ── Profile ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_profile_me_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/me")
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_profile_change_password_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/v1/me/change-password", json={
            "current_password": "x",
            "new_password": "y",
        })
        assert resp.status_code == 401


# ── Templates ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_templates_list_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/templates")
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_templates_create_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/v1/templates", json={"name": "T", "content": "C"})
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_templates_crud():
    await _register()
    if not _token:
        pytest.skip("No se pudo autenticar")

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        name = f"T-{uuid.uuid4().hex[:6]}"
        resp = await c.post("/api/v1/templates", json={"name": name, "content": "Hello"}, headers=_headers())
        assert resp.status_code == 201
        tid = resp.json()["id"]

        resp = await c.get(f"/api/v1/templates", headers=_headers())
        assert resp.status_code == 200
        ids = [t["id"] for t in resp.json()]
        assert tid in ids

        resp = await c.patch(f"/api/v1/templates/{tid}", json={"name": name, "content": "Updated"}, headers=_headers())
        assert resp.status_code == 200

        resp = await c.delete(f"/api/v1/templates/{tid}", headers=_headers())
        assert resp.status_code == 204


# ── Automations ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_automations_list_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/automations")
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_automations_create_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/v1/automations", json={"name": "F", "trigger": "new_contact"})
        assert resp.status_code == 401


# ── Team ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_team_list_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/team")
        assert resp.status_code == 401


# ── Knowledge Base ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_kb_list_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/knowledge-base")
        assert resp.status_code == 401


# ── Conversations ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_conversations_list_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/conversations")
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_conversations_reply_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(f"/api/v1/conversations/{uuid.uuid4()}/reply", json={"text": "hola"})
        assert resp.status_code == 401


# ── Payments ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_plans_public():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/plans")
        assert resp.status_code == 200
        assert "starter" in resp.json()


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_checkout_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/v1/checkout/create-session", json={"plan": "starter"})
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_transactions_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/transactions")
        assert resp.status_code == 401


# ── Radio ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_radio_voices_public():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/radio/voices")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        assert data[0]["id"] == "es-MX-JorgeNeural"


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_radio_audio_404_for_invalid():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/radio/audio/nonexistent.ogg")
        assert resp.status_code == 404


# ── Analytics ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_analytics_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/analytics/optimal-send-time")
        assert resp.status_code == 401
