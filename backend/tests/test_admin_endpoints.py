"""Real-DB integration tests for admin.py's handler functions — called
directly (not through TestClient/HTTP) to sidestep the cross-event-loop
issues TestClient causes when mixed with real-DB seeding in this repo (see
memory: pooled asyncpg connections need engine.dispose() at both ends of
each real-DB test). The authorization gate itself (require_admin) has its
own focused unit tests in test_admin_auth.py — this file only covers what
each handler actually does once past that gate. Zero coverage existed
before this file."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.api.v1.admin import (
    get_subscription,
    list_subscriptions,
    list_user_transactions,
    list_users,
    platform_stats,
    update_subscription,
    SubscriptionUpdateRequest,
)
from app.database import AsyncSessionLocal, engine
from app.models.transaction import Transaction
from app.models.user import User


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Transaction).where(Transaction.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestListSubscriptions:
    @pytest.mark.asyncio
    async def test_filters_by_status_and_paginates(self):
        await engine.dispose()
        run_id = uuid.uuid4().hex[:8]
        async with AsyncSessionLocal() as db:
            active = User(email=f"active-{run_id}@test.com", password_hash="x", subscription_status="active")
            trial = User(email=f"trial-{run_id}@test.com", password_hash="x", subscription_status="trial")
            db.add_all([active, trial])
            await db.commit()
            user_ids = [active.id, trial.id]

        try:
            async with AsyncSessionLocal() as db:
                result = await list_subscriptions(page=1, per_page=20, status_filter="active", db=db)
            emails = [u.email for u in result["users"]]
            assert f"active-{run_id}@test.com" in emails
            assert f"trial-{run_id}@test.com" not in emails
        finally:
            await _cleanup(user_ids)


class TestGetSubscription:
    @pytest.mark.asyncio
    async def test_returns_user_details(self):
        await engine.dispose()
        run_id = uuid.uuid4().hex[:8]
        async with AsyncSessionLocal() as db:
            user = User(email=f"get-{run_id}@test.com", password_hash="x", current_plan="growth")
            db.add(user)
            await db.commit()
            user_id = user.id

        try:
            async with AsyncSessionLocal() as db:
                result = await get_subscription(user_id=str(user_id), db=db)
            assert result.email == f"get-{run_id}@test.com"
            assert result.current_plan == "growth"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_unknown_user_returns_404(self):
        from fastapi import HTTPException
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc_info:
                await get_subscription(user_id=str(uuid.uuid4()), db=db)
        assert exc_info.value.status_code == 404


class TestUpdateSubscription:
    @pytest.mark.asyncio
    async def test_updates_only_provided_fields(self):
        await engine.dispose()
        run_id = uuid.uuid4().hex[:8]
        async with AsyncSessionLocal() as db:
            user = User(
                email=f"upd-{run_id}@test.com", password_hash="x",
                current_plan="trial", messages_remaining=50,
            )
            db.add(user)
            await db.commit()
            user_id = user.id

        try:
            async with AsyncSessionLocal() as db:
                body = SubscriptionUpdateRequest(current_plan="growth")
                result = await update_subscription(user_id=str(user_id), body=body, db=db)
            assert result.current_plan == "growth"
            assert result.messages_remaining == 50  # untouched field preserved
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_unknown_user_returns_404(self):
        from fastapi import HTTPException
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc_info:
                await update_subscription(
                    user_id=str(uuid.uuid4()), body=SubscriptionUpdateRequest(current_plan="pro"), db=db,
                )
        assert exc_info.value.status_code == 404


class TestListUserTransactions:
    @pytest.mark.asyncio
    async def test_lists_only_that_users_transactions(self):
        await engine.dispose()
        run_id = uuid.uuid4().hex[:8]
        async with AsyncSessionLocal() as db:
            user_a = User(email=f"txa-{run_id}@test.com", password_hash="x")
            user_b = User(email=f"txb-{run_id}@test.com", password_hash="x")
            db.add_all([user_a, user_b])
            await db.flush()
            db.add(Transaction(advertiser_id=user_a.id, amount=Decimal("199.00"), currency="MXN", status="succeeded"))
            db.add(Transaction(advertiser_id=user_b.id, amount=Decimal("99.00"), currency="MXN", status="succeeded"))
            await db.commit()
            user_ids = [user_a.id, user_b.id]

        try:
            async with AsyncSessionLocal() as db:
                result = await list_user_transactions(user_id=str(user_ids[0]), page=1, per_page=20, db=db)
            assert result["total"] == 1
            assert float(result["transactions"][0].amount) == 199.0
        finally:
            await _cleanup(user_ids)

    @pytest.mark.asyncio
    async def test_unknown_user_returns_404(self):
        from fastapi import HTTPException
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc_info:
                await list_user_transactions(user_id=str(uuid.uuid4()), page=1, per_page=20, db=db)
        assert exc_info.value.status_code == 404


class TestListUsers:
    @pytest.mark.asyncio
    async def test_search_matches_email_or_business_name(self):
        await engine.dispose()
        run_id = uuid.uuid4().hex[:8]
        async with AsyncSessionLocal() as db:
            match = User(email=f"findme-{run_id}@test.com", password_hash="x", business_name="Panadería Findable")
            nomatch = User(email=f"other-{run_id}@test.com", password_hash="x", business_name="Otro Negocio")
            db.add_all([match, nomatch])
            await db.commit()
            user_ids = [match.id, nomatch.id]

        try:
            async with AsyncSessionLocal() as db:
                result = await list_users(page=1, per_page=20, status_filter=None, plan_filter=None, search="findme", db=db)
            emails = [u.email for u in result["users"]]
            assert f"findme-{run_id}@test.com" in emails
            assert f"other-{run_id}@test.com" not in emails
        finally:
            await _cleanup(user_ids)


class TestPlatformStats:
    @pytest.mark.asyncio
    async def test_returns_all_expected_keys(self):
        async with AsyncSessionLocal() as db:
            result = await platform_stats(db=db)
        for key in (
            "total_users", "users_trial", "users_active", "users_suspended",
            "users_churned", "mrr_mxn", "mrr_usd", "messages_sent_today",
            "messages_sent_month", "new_users_this_month", "stripe_connected",
        ):
            assert key in result
