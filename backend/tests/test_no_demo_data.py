"""Una cuenta nueva arranca vacía: verificar el correo no le crea contactos
inventados, ni una campaña de ejemplo, ni un documento de conocimiento que
hable de IaRadio (con el que su bot contestaba como si fuera IaRadio)."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.core.redis import close_redis
from app.database import AsyncSessionLocal, engine
from app.main import app
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User


@pytest.mark.asyncio
async def test_verified_account_starts_without_fake_data():
    await engine.dispose()
    await close_redis()
    email = f"vacia-{uuid.uuid4().hex[:8]}@test.com"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/auth/register",
                             json={"email": email, "password": "TestPass1", "business_name": "Negocio Vacío"})
            assert r.status_code == 201, r.text

            import redis.asyncio as aioredis

            from app.config import settings
            rd = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                code = await rd.get(f"email_verify:{email}")
            finally:
                await rd.aclose()
            r = await c.post("/api/v1/auth/verify-email", json={"email": email, "code": code})
            assert r.status_code == 200, r.text

        async with AsyncSessionLocal() as db:
            user_id = (await db.execute(select(User.id).where(User.email == email))).scalar_one()
            for model in (Contact, Campaign, KnowledgeBase):
                n = (await db.execute(select(func.count()).select_from(model).where(model.advertiser_id == user_id))).scalar_one()
                assert n == 0, f"{model.__name__}: {n}"
    finally:
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.email == email))
            await db.commit()
