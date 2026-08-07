"""Real HTTP + real DB regression test for POST /api/v1/contacts.

This endpoint had zero test coverage (a known gap — see project notes)
and was silently 500ing on EVERY call in production: it unconditionally
calls dispatch_webhook_event() right after creating the contact, with no
try/except, and that function's query used UserWebhook.events.any(event)
— an ARRAY-comparator method that raises AttributeError on the JSONB
column this project actually uses. Uses httpx.AsyncClient + ASGITransport
(shares this test's event loop) rather than starlette's TestClient, which
runs in a separate thread/event loop that conflicts with this repo's
real-DB session style.
"""
import uuid

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

from app.core.security import create_access_token, hash_password
from app.database import AsyncSessionLocal, engine
from app.main import app
from app.models.contact import Contact
from app.models.user import User
from app.models.user_webhook import UserWebhook


async def _seed_verified_user():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(
            email=f"{uuid.uuid4()}@test.com", password_hash=hash_password("pw12345678"),
            role="advertiser", email_verified=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.id


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(UserWebhook).where(UserWebhook.user_id == user_id))
        await db.execute(delete(Contact).where(Contact.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_contact_does_not_500_with_active_webhook_subscribed():
    user_id = _sub = None
    try:
        user_id = await _seed_verified_user()

        async with AsyncSessionLocal() as db:
            db.add(UserWebhook(
                user_id=user_id, name="Zapier", url="https://hooks.example.com/x",
                events=["contact.created"], secret="whsec",
            ))
            await db.commit()

        token = create_access_token(subject=str(user_id), role="advertiser")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/contacts",
                json={"name": "Cliente Nuevo", "phone": "+525511112222"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "Cliente Nuevo"
    finally:
        if user_id:
            await _cleanup(user_id)
