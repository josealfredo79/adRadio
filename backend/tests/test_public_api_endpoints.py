"""Real-DB integration tests for public_api.py (API key CRUD, JWT-authed)
and public_api_routes.py (the external, API-key-scoped /public/* endpoints
— the highest-risk surface in the app since it's meant for third-party
clients). Handler functions called directly, same rationale as
test_admin_endpoints.py. The auth dependency itself (require_api_key_scope)
has its own unit tests in test_api_key_auth.py. Zero coverage existed
before this file."""
import uuid
from decimal import Decimal

import pytest
from unittest.mock import MagicMock

from fastapi import HTTPException
from sqlalchemy import delete

from app.api.v1.public_api import ApiKeyCreate, create_api_key, deactivate_api_key, delete_api_key, list_api_keys
from app.api.v1.public_api_routes import public_list_campaigns, public_list_contacts
from app.database import AsyncSessionLocal, engine
from app.models.api_key import ApiKey
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.user import User


async def _seed_user(current_plan: str = "business"):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(
            email=f"{uuid.uuid4()}@test.com", password_hash="x",
            current_plan=current_plan, subscription_status="active",
        )
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Campaign).where(Campaign.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
        await db.execute(delete(ApiKey).where(ApiKey.user_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestApiKeyCrud:
    @pytest.mark.asyncio
    async def test_create_list_deactivate_delete_roundtrip(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_api_key(
                    request=MagicMock(headers={}), body=ApiKeyCreate(name="Test Key", scopes=["campaigns:read"]),
                    db=db, current_user=user, _=None, redis=None,
                )
            assert created.key.startswith("iar_")
            assert created.prefix == created.key[:8]

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                keys = await list_api_keys(db=db, current_user=user)
            assert len(keys) == 1
            assert keys[0].name == "Test Key"

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                deactivated = await deactivate_api_key(key_id=created.id, db=db, current_user=user)
            assert deactivated.active is False

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await delete_api_key(key_id=created.id, db=db, current_user=user)
                keys_after = await list_api_keys(db=db, current_user=user)
            assert keys_after == []
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_cannot_delete_another_users_key(self):
        """Ownership scoping: the query filters ApiKey.user_id ==
        current_user.id, so a key_id that exists but belongs to someone
        else must 404, not delete it."""
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                created = await create_api_key(
                    request=MagicMock(headers={}), body=ApiKeyCreate(name="Owner's Key", scopes=[]),
                    db=db, current_user=owner, _=None, redis=None,
                )

            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc_info:
                    await delete_api_key(key_id=created.id, db=db, current_user=other)
                assert exc_info.value.status_code == 404

            # Still there — the wrong-owner delete attempt must not have worked.
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                keys = await list_api_keys(db=db, current_user=owner)
            assert len(keys) == 1
        finally:
            await _cleanup([owner_id, other_id])

    @pytest.mark.asyncio
    async def test_delete_unknown_key_returns_404(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await delete_api_key(key_id=uuid.uuid4(), db=db, current_user=user)
            assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])


class TestPublicListCampaigns:
    @pytest.mark.asyncio
    async def test_only_returns_own_campaigns(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Campaign(advertiser_id=owner_id, name="Mía", type="promo", message_text="hola"))
                db.add(Campaign(advertiser_id=other_id, name="Ajena", type="promo", message_text="hola"))
                await db.commit()

            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                result = await public_list_campaigns(page=1, page_size=20, db=db, current_user=owner)
            names = [c.name for c in result["items"]]
            assert names == ["Mía"]
        finally:
            await _cleanup([owner_id, other_id])

    @pytest.mark.asyncio
    async def test_plan_without_api_access_gets_402(self):
        user_id = await _seed_user(current_plan="trial")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await public_list_campaigns(page=1, page_size=20, db=db, current_user=user)
            assert exc_info.value.status_code == 402
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_business_plan_has_api_access(self):
        user_id = await _seed_user(current_plan="business")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result = await public_list_campaigns(page=1, page_size=20, db=db, current_user=user)
            assert result["items"] == []
            assert result["total"] == 0
        finally:
            await _cleanup([user_id])


class TestPublicListContacts:
    @pytest.mark.asyncio
    async def test_only_returns_own_contacts(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Contact(advertiser_id=owner_id, name="Mío", phone="+521111111111", status="active"))
                db.add(Contact(advertiser_id=other_id, name="Ajeno", phone="+522222222222", status="active"))
                await db.commit()

            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                result = await public_list_contacts(page=1, page_size=20, db=db, current_user=owner)
            assert len(result.items) == 1
            assert result.items[0].name == "Mío"
        finally:
            await _cleanup([owner_id, other_id])

    @pytest.mark.asyncio
    async def test_plan_without_api_access_gets_402(self):
        user_id = await _seed_user(current_plan="growth")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await public_list_contacts(page=1, page_size=20, db=db, current_user=user)
            assert exc_info.value.status_code == 402
        finally:
            await _cleanup([user_id])
