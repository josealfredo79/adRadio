"""Real-DB integration tests for user_webhooks.py — zero coverage existed
before this file, and it had the same bug pattern already found twice
elsewhere this session (admin.py TransactionResponse, public_api.py
ApiKeyOut/ApiKeyCreatedOut): a Pydantic response model field typed `str`
that actually receives a `datetime` from the ORM, with no validator to
bridge it. Here it was UserWebhookOut.created_at — every endpoint that
returns webhook data (create, update, and list whenever the user has ≥1
webhook) 500'd unconditionally. Fixed by typing the field `datetime`
instead (see app/api/v1/user_webhooks.py)."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.api.v1.user_webhooks import (
    UserWebhookCreate,
    UserWebhookUpdate,
    create_webhook,
    delete_webhook,
    list_webhooks,
    update_webhook,
)
from app.api.v1.user_webhooks import test_webhook as ping_webhook
from app.database import AsyncSessionLocal, engine
from app.models.user import User
from app.models.user_webhook import UserWebhook


async def _seed_user():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x")
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(UserWebhook).where(UserWebhook.user_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestCreateAndListWebhooks:
    @pytest.mark.asyncio
    async def test_create_then_list_returns_it(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_webhook(
                    body=UserWebhookCreate(name="Mi Webhook", url="https://example.com/hook", events=["campaign.sent"]),
                    db=db, current_user=user,
                )
            assert created.name == "Mi Webhook"
            assert created.active is True
            assert created.created_at is not None  # the exact bug this file guards against

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                webhooks = await list_webhooks(db=db, current_user=user)
            assert len(webhooks) == 1
            assert webhooks[0].id == created.id
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_list_only_returns_own_webhooks(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                await create_webhook(
                    body=UserWebhookCreate(name="Mío", url="https://example.com/a", events=[]),
                    db=db, current_user=owner,
                )
                other = await db.get(User, other_id)
                await create_webhook(
                    body=UserWebhookCreate(name="Ajeno", url="https://example.com/b", events=[]),
                    db=db, current_user=other,
                )

            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                webhooks = await list_webhooks(db=db, current_user=owner)
            assert [w.name for w in webhooks] == ["Mío"]
        finally:
            await _cleanup([owner_id, other_id])

    @pytest.mark.asyncio
    async def test_list_empty_when_no_webhooks(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                webhooks = await list_webhooks(db=db, current_user=user)
            assert webhooks == []
        finally:
            await _cleanup([user_id])


class TestUpdateWebhook:
    @pytest.mark.asyncio
    async def test_updates_only_provided_fields(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_webhook(
                    body=UserWebhookCreate(name="Original", url="https://example.com/hook", events=["a"]),
                    db=db, current_user=user,
                )

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                updated = await update_webhook(
                    webhook_id=created.id, body=UserWebhookUpdate(active=False), db=db, current_user=user,
                )
            assert updated.active is False
            assert updated.name == "Original"  # untouched
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_cannot_update_another_users_webhook(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                created = await create_webhook(
                    body=UserWebhookCreate(name="Owner's", url="https://example.com/hook", events=[]),
                    db=db, current_user=owner,
                )

            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc_info:
                    await update_webhook(
                        webhook_id=created.id, body=UserWebhookUpdate(active=False), db=db, current_user=other,
                    )
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([owner_id, other_id])

    @pytest.mark.asyncio
    async def test_unknown_webhook_returns_404(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await update_webhook(
                        webhook_id=uuid.uuid4(), body=UserWebhookUpdate(active=False), db=db, current_user=user,
                    )
            assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])


class TestDeleteWebhook:
    @pytest.mark.asyncio
    async def test_deletes_and_disappears_from_list(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_webhook(
                    body=UserWebhookCreate(name="Temp", url="https://example.com/hook", events=[]),
                    db=db, current_user=user,
                )

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await delete_webhook(webhook_id=created.id, db=db, current_user=user)
                webhooks = await list_webhooks(db=db, current_user=user)
            assert webhooks == []
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_cannot_delete_another_users_webhook(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                created = await create_webhook(
                    body=UserWebhookCreate(name="Owner's", url="https://example.com/hook", events=[]),
                    db=db, current_user=owner,
                )

            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc_info:
                    await delete_webhook(webhook_id=created.id, db=db, current_user=other)
                assert exc_info.value.status_code == 404

            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                webhooks = await list_webhooks(db=db, current_user=owner)
            assert len(webhooks) == 1
        finally:
            await _cleanup([owner_id, other_id])


class TestPingWebhook:
    @pytest.mark.asyncio
    async def test_successful_ping_signs_body_and_reports_success(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_webhook(
                    body=UserWebhookCreate(name="Pingable", url="https://example.com/hook", events=[]),
                    db=db, current_user=user,
                )

            fake_response = MagicMock(is_success=True, status_code=200)
            fake_client = AsyncMock()
            fake_client.post = AsyncMock(return_value=fake_response)
            fake_client.__aenter__ = AsyncMock(return_value=fake_client)
            fake_client.__aexit__ = AsyncMock(return_value=False)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with patch("httpx.AsyncClient", return_value=fake_client):
                    result = await ping_webhook(webhook_id=created.id, db=db, current_user=user)

            assert result.success is True
            assert result.status_code == 200
            sent_headers = fake_client.post.call_args.kwargs["headers"]
            assert "X-Webhook-Signature" in sent_headers
            assert sent_headers["X-Webhook-Event"] == "test.ping"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_network_failure_reports_error_not_raise(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_webhook(
                    body=UserWebhookCreate(name="Unreachable", url="https://does-not-exist.invalid/hook", events=[]),
                    db=db, current_user=user,
                )

            fake_client = AsyncMock()
            fake_client.post = AsyncMock(side_effect=Exception("connection refused"))
            fake_client.__aenter__ = AsyncMock(return_value=fake_client)
            fake_client.__aexit__ = AsyncMock(return_value=False)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with patch("httpx.AsyncClient", return_value=fake_client):
                    result = await ping_webhook(webhook_id=created.id, db=db, current_user=user)

            assert result.success is False
            assert "connection refused" in result.error
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_unknown_webhook_returns_404(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await ping_webhook(webhook_id=uuid.uuid4(), db=db, current_user=user)
            assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])
