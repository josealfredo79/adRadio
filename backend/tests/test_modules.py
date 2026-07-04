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


async def _get_verification_code(email: str) -> str | None:
    """Read the email-verification code straight from Redis — the same
    instance the app uses (settings.REDIS_URL) — so tests can complete the
    real verify-email flow instead of stubbing it out."""
    try:
        import redis.asyncio as aioredis
        from app.config import settings
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            return await r.get(f"email_verify:{email}")
        finally:
            await r.aclose()
    except Exception:
        return None


async def _register():
    """Register (or reuse) a real advertiser account and cache a bearer token.

    /auth/register does not return a token, and /auth/login rejects
    unverified accounts — so a real end-to-end flow has to register, fetch
    the emailed verification code from Redis, verify, then log in.
    """
    global _token
    if _token:
        return

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/register", json={
            "email": AUTH_EMAIL,
            "password": AUTH_PASS,
            "business_name": "Module Test",
        })
        if r.status_code not in (201, 409):
            return

        code = await _get_verification_code(AUTH_EMAIL)
        if code:
            await c.post("/api/v1/auth/verify-email", json={"email": AUTH_EMAIL, "code": code})

        r2 = await c.post("/api/v1/auth/login", json={
            "email": AUTH_EMAIL,
            "password": AUTH_PASS,
        })
        if r2.status_code == 200:
            _token = r2.json().get("access_token")


def _headers():
    return {"Authorization": f"Bearer {_token}"} if _token else {}


async def _set_current_plan(plan: str) -> None:
    """Directly bump the test advertiser's plan in the DB (bypasses Stripe).
    Needed to exercise plan-gated flows (e.g. knowledge-base upload requires
    Growth+) without wiring a real payment."""
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == AUTH_EMAIL))
        user = result.scalar_one_or_none()
        if user:
            user.current_plan = plan
            await db.commit()


@pytest.fixture(autouse=True)
async def _reset_async_singletons():
    """
    Force fresh DB/Redis connections bound to the *current* test's event loop.

    `app.database.engine` and `app.core.redis._redis_pool` are lazy
    module-level singletons that pool live connections tied to whichever
    event loop was running when they were first created. That's fine in
    production (one process = one long-lived loop), but under
    pytest-asyncio each test function gets its own event loop, so a
    connection pooled during one integration test raises "Event loop is
    closed" / "attached to a different loop" the moment a later test in
    this file tries to reuse it. Disposing/clearing here avoids that.
    """
    try:
        from app.database import engine
        await engine.dispose()
    except Exception:
        pass
    try:
        import app.core.redis as redis_module
        if redis_module._redis_pool is not None:
            try:
                await redis_module._redis_pool.aclose()
            except Exception:
                pass
            redis_module._redis_pool = None
    except Exception:
        pass
    yield


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


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_kb_upload_requires_growth_plan():
    """Trial-plan advertisers are gated out of RAG (Growth+ only) with a 402."""
    await _register()
    if not _token:
        pytest.skip("No se pudo autenticar")
    await _set_current_plan("trial")

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/knowledge-base/upload",
            files={"file": ("test.txt", b"hola mundo", "text/plain")},
            headers=_headers(),
        )
        assert resp.status_code == 402


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_kb_upload_list_delete_on_growth_plan():
    await _register()
    if not _token:
        pytest.skip("No se pudo autenticar")
    await _set_current_plan("growth")

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/knowledge-base/upload",
            files={"file": ("test.txt", b"hola mundo", "text/plain")},
            headers=_headers(),
        )
        assert resp.status_code == 202
        file_id = resp.json()["id"]

        resp = await c.get("/api/v1/knowledge-base", headers=_headers())
        assert resp.status_code == 200
        ids = [f["id"] for f in resp.json()]
        assert file_id in ids

        resp = await c.delete(f"/api/v1/knowledge-base/{file_id}", headers=_headers())
        assert resp.status_code == 204


# ── Appointments ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_appointments_list_requires_auth():
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/appointments")
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_appointments_crud():
    await _register()
    if not _token:
        pytest.skip("No se pudo autenticar")

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/v1/appointments", json={
            "customer_name": "Cliente Test",
            "service": "Corte",
            "scheduled_at": "2026-08-01T15:00:00Z",
        }, headers=_headers())
        assert resp.status_code == 201
        aid = resp.json()["id"]
        assert resp.json()["status"] == "confirmed" or resp.json()["status"]

        resp = await c.get("/api/v1/appointments", headers=_headers())
        assert resp.status_code == 200
        ids = [a["id"] for a in resp.json()]
        assert aid in ids

        resp = await c.patch(f"/api/v1/appointments/{aid}", json={"status": "completed"}, headers=_headers())
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

        resp = await c.delete(f"/api/v1/appointments/{aid}", headers=_headers())
        assert resp.status_code == 204


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_appointments_update_delete_404_for_missing():
    await _register()
    if not _token:
        pytest.skip("No se pudo autenticar")

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.patch(f"/api/v1/appointments/{uuid.uuid4()}", json={"status": "completed"}, headers=_headers())
        assert resp.status_code == 404

        resp = await c.delete(f"/api/v1/appointments/{uuid.uuid4()}", headers=_headers())
        assert resp.status_code == 404


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


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_transactions_list_authenticated():
    await _register()
    if not _token:
        pytest.skip("No se pudo autenticar")

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/transactions", headers=_headers())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_checkout_invalid_plan_rejected():
    """Invalid plan keys are rejected before any Stripe call is made."""
    await _register()
    if not _token:
        pytest.skip("No se pudo autenticar")

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/v1/checkout/create-session", json={"plan": "not-a-real-plan"}, headers=_headers())
        assert resp.status_code == 400


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


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_APP or not HAS_DB, reason=db_reason)
async def test_analytics_summary_authenticated():
    await _register()
    if not _token:
        pytest.skip("No se pudo autenticar")

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/analytics/summary", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"totals", "rates", "business"}

        resp = await c.get("/api/v1/analytics/optimal-send-time", headers=_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["hours"]) == 24

        resp = await c.get("/api/v1/analytics/campaign-performance", headers=_headers())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
