"""Tests for payments.py — plan catalog and the pricing-strategy features
built on top of it (tier Micro, programa Fundadores, pago anual, referidos)."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.api.v1.payments import (
    PLANS, PLAN_MESSAGES, FOUNDER_PRICES,
    CheckoutSessionBody, create_checkout_session, founder_status, _claim_founder_slot,
)
from app.api.deps import PLAN_ORDER, PLAN_RADIO_LIMITS, check_feature_access
from app.core.security import generate_referral_code, hash_password
from app.database import AsyncSessionLocal, engine
from app.models.founder_program import FounderProgram
from app.models.user import User


async def _seed_user(current_plan: str = "trial", **kwargs):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(
            email=f"{uuid.uuid4()}@test.com", password_hash=hash_password("x"),
            current_plan=current_plan, subscription_status="active",
            **kwargs,
        )
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


async def _set_founder_slots(total: int, used: int):
    """Overwrite the singleton founder_program row for a deterministic test scenario."""
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(FounderProgram).limit(1))
        program = result.scalar_one()
        original = (program.slots_total, program.slots_used)
        program.slots_total = total
        program.slots_used = used
        await db.commit()
    return original


async def _restore_founder_slots(original: tuple[int, int]):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(FounderProgram).limit(1))
        program = result.scalar_one()
        program.slots_total, program.slots_used = original
        await db.commit()
    await engine.dispose()


def _fake_request():
    req = AsyncMock()
    req.headers.get.return_value = "fake_sig"
    req.body = AsyncMock(return_value=b"{}")
    return req


class TestMicroPlan:
    def test_micro_plan_exists_below_starter_price(self):
        assert "micro" in PLANS
        assert PLANS["micro"]["price_mxn"] < PLANS["starter"]["price_mxn"]
        assert PLANS["micro"]["messages"] < PLANS["starter"]["messages"]

    def test_micro_plan_messages_in_plan_messages_map(self):
        assert PLAN_MESSAGES["micro"] == PLANS["micro"]["messages"]

    def test_micro_is_ordered_below_starter(self):
        assert PLAN_ORDER.index("micro") < PLAN_ORDER.index("starter")
        assert PLAN_ORDER.index("trial") < PLAN_ORDER.index("micro")

    def test_micro_has_no_radio_ads(self):
        assert PLAN_RADIO_LIMITS["micro"] == 0

    @pytest.mark.asyncio
    async def test_micro_user_does_not_get_rag_feature(self):
        user_id = await _seed_user(current_plan="micro")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                assert check_feature_access(user, "rag") is False
        finally:
            await _cleanup([user_id])


class TestFounderProgram:
    def test_founder_prices_only_cover_starter_and_growth(self):
        assert set(FOUNDER_PRICES.keys()) == {"starter", "growth"}
        for plan_key, founder_price in FOUNDER_PRICES.items():
            assert founder_price["price_mxn"] < PLANS[plan_key]["price_mxn"]

    @pytest.mark.asyncio
    async def test_claim_slot_succeeds_and_increments(self):
        original = await _set_founder_slots(total=5, used=2)
        try:
            async with AsyncSessionLocal() as db:
                claimed = await _claim_founder_slot(db)
            assert claimed is True
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(FounderProgram).limit(1))
                assert result.scalar_one().slots_used == 3
        finally:
            await _restore_founder_slots(original)

    @pytest.mark.asyncio
    async def test_claim_slot_fails_when_exhausted(self):
        original = await _set_founder_slots(total=5, used=5)
        try:
            async with AsyncSessionLocal() as db:
                claimed = await _claim_founder_slot(db)
            assert claimed is False
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(FounderProgram).limit(1))
                assert result.scalar_one().slots_used == 5  # unchanged, not oversold
        finally:
            await _restore_founder_slots(original)

    @pytest.mark.asyncio
    async def test_concurrent_claims_never_oversell(self):
        """The atomic UPDATE...WHERE...RETURNING must let exactly N claims
        succeed out of N+extra concurrent attempts, never more."""
        original = await _set_founder_slots(total=3, used=0)
        try:
            async def claim():
                async with AsyncSessionLocal() as db:
                    return await _claim_founder_slot(db)

            results = await asyncio.gather(*[claim() for _ in range(8)])
            assert sum(1 for r in results if r) == 3
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(FounderProgram).limit(1))
                assert result.scalar_one().slots_used == 3
        finally:
            await _restore_founder_slots(original)

    @pytest.mark.asyncio
    async def test_founder_status_reflects_real_slots(self):
        original = await _set_founder_slots(total=25, used=20)
        try:
            async with AsyncSessionLocal() as db:
                out = await founder_status(db)
            assert out == {
                "available": True, "slots_left": 5, "slots_total": 25, "prices": FOUNDER_PRICES,
            }
        finally:
            await _restore_founder_slots(original)

    @pytest.mark.asyncio
    async def test_founder_status_unavailable_when_exhausted(self):
        original = await _set_founder_slots(total=25, used=25)
        try:
            async with AsyncSessionLocal() as db:
                out = await founder_status(db)
            assert out["available"] is False
            assert out["slots_left"] == 0
        finally:
            await _restore_founder_slots(original)

    @pytest.mark.asyncio
    async def test_checkout_rejects_founder_on_ineligible_plan(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await create_checkout_session(
                        request=_fake_request(),
                        body=CheckoutSessionBody(plan="pro", founder=True),
                        current_user=user, db=db, _=None, redis=None,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_checkout_rejects_founder_plus_annual_combo(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await create_checkout_session(
                        request=_fake_request(),
                        body=CheckoutSessionBody(plan="starter", founder=True, billing_cycle="annual"),
                        current_user=user, db=db, _=None, redis=None,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_checkout_returns_409_when_slots_exhausted(self):
        user_id = await _seed_user()
        original = await _set_founder_slots(total=1, used=1)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await create_checkout_session(
                        request=_fake_request(),
                        body=CheckoutSessionBody(plan="starter", founder=True),
                        current_user=user, db=db, _=None, redis=None,
                    )
                assert exc_info.value.status_code == 409
        finally:
            await _restore_founder_slots(original)
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_checkout_uses_founder_price_and_does_not_double_claim_on_retry(self):
        """The 'No such customer' retry path must not claim a second slot
        for the same request — this was a real bug caught during review."""
        user_id = await _seed_user()
        original = await _set_founder_slots(total=5, used=0)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)

                fake_session = MagicMock(url="https://checkout.stripe.com/fake")
                with patch("app.api.v1.payments._resolve_stripe_customer", new=AsyncMock(return_value="cus_fake")), \
                     patch("app.api.v1.payments.stripe_lib.checkout.Session.create", return_value=fake_session) as mock_create, \
                     patch("app.api.v1.payments.settings") as mock_settings, \
                     patch("app.api.v1.payments.store_idempotency_response", new=AsyncMock()):
                    mock_settings.STRIPE_SECRET_KEY = "sk_test_fake"
                    mock_settings.FRONTEND_URL = "https://iaradio.online"
                    out = await create_checkout_session(
                        request=_fake_request(),
                        body=CheckoutSessionBody(plan="starter", founder=True),
                        current_user=user, db=db, _=None, redis=None,
                    )
            assert out == {"checkout_url": "https://checkout.stripe.com/fake"}
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["line_items"][0]["price_data"]["unit_amount"] == FOUNDER_PRICES["starter"]["price_usd"] * 100
            assert call_kwargs["metadata"]["founder"] == "true"

            async with AsyncSessionLocal() as db:
                result = await db.execute(select(FounderProgram).limit(1))
                assert result.scalar_one().slots_used == 1  # claimed exactly once
        finally:
            await _restore_founder_slots(original)
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_webhook_checkout_completed_sets_is_founder(self):
        from app.api.v1.webhooks_pkg.stripe import stripe_webhook

        user_id = await _seed_user()
        try:
            mock_event = {
                "id": "evt_founder_1",
                "type": "checkout.session.completed",
                "data": {"object": {
                    "customer": "cus_founder_test",
                    "metadata": {"plan": "starter", "user_id": str(user_id), "founder": "true", "billing_cycle": "monthly"},
                    "amount_total": 34900,
                    "currency": "usd",
                    "payment_intent": f"pi_founder_{uuid.uuid4()}",
                }},
            }
            async with AsyncSessionLocal() as db:
                u = await db.get(User, user_id)
                u.stripe_customer_id = "cus_founder_test"
                await db.commit()

            with patch("app.api.v1.webhooks_pkg.stripe.settings") as mock_settings, \
                 patch("stripe.Webhook.construct_event", return_value=mock_event):
                mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
                async with AsyncSessionLocal() as db:
                    await stripe_webhook(_fake_request(), db)

            async with AsyncSessionLocal() as db:
                reloaded = await db.get(User, user_id)
                assert reloaded.is_founder is True
                assert reloaded.current_plan == "starter"
        finally:
            await _cleanup([user_id])


class TestAnnualBilling:
    @pytest.mark.asyncio
    async def test_checkout_annual_uses_10x_monthly_price_and_year_interval(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                fake_session = MagicMock(url="https://checkout.stripe.com/fake")
                with patch("app.api.v1.payments._resolve_stripe_customer", new=AsyncMock(return_value="cus_fake")), \
                     patch("app.api.v1.payments.stripe_lib.checkout.Session.create", return_value=fake_session) as mock_create, \
                     patch("app.api.v1.payments.settings") as mock_settings, \
                     patch("app.api.v1.payments.store_idempotency_response", new=AsyncMock()):
                    mock_settings.STRIPE_SECRET_KEY = "sk_test_fake"
                    mock_settings.FRONTEND_URL = "https://iaradio.online"
                    await create_checkout_session(
                        request=_fake_request(),
                        body=CheckoutSessionBody(plan="growth", billing_cycle="annual"),
                        current_user=user, db=db, _=None, redis=None,
                    )
            call_kwargs = mock_create.call_args.kwargs
            price_data = call_kwargs["line_items"][0]["price_data"]
            assert price_data["unit_amount"] == PLANS["growth"]["price_usd"] * 10 * 100
            assert price_data["recurring"]["interval"] == "year"
            assert call_kwargs["metadata"]["billing_cycle"] == "annual"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_webhook_checkout_completed_annual_sets_billing_cycle_and_refill(self):
        from app.api.v1.webhooks_pkg.stripe import stripe_webhook

        user_id = await _seed_user()
        try:
            mock_event = {
                "id": "evt_annual_1",
                "type": "checkout.session.completed",
                "data": {"object": {
                    "customer": "cus_annual_test",
                    "metadata": {"plan": "growth", "user_id": str(user_id), "founder": "false", "billing_cycle": "annual"},
                    "amount_total": 59000 * 10,
                    "currency": "usd",
                    "payment_intent": f"pi_annual_{uuid.uuid4()}",
                }},
            }
            async with AsyncSessionLocal() as db:
                u = await db.get(User, user_id)
                u.stripe_customer_id = "cus_annual_test"
                await db.commit()

            before = datetime.now(timezone.utc)
            with patch("app.api.v1.webhooks_pkg.stripe.settings") as mock_settings, \
                 patch("stripe.Webhook.construct_event", return_value=mock_event):
                mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
                async with AsyncSessionLocal() as db:
                    await stripe_webhook(_fake_request(), db)

            async with AsyncSessionLocal() as db:
                reloaded = await db.get(User, user_id)
                assert reloaded.billing_cycle == "annual"
                assert reloaded.messages_refill_at is not None
                assert before + timedelta(days=29) < reloaded.messages_refill_at < before + timedelta(days=31)
                # plan_expires_at debe cubrir el año completo, no solo 30 días
                assert reloaded.plan_expires_at > before + timedelta(days=300)
        finally:
            await _cleanup([user_id])

    def test_replenish_annual_message_quota_tops_up_and_advances_cycle(self):
        # Plain sync test (not @pytest.mark.asyncio): replenish_annual_message_quota()
        # manages its own event loop internally via run_async/asyncio.run, which
        # cannot be called from inside a loop pytest-asyncio already has running —
        # so seeding/cleanup each get their own separate asyncio.run() call.
        from app.workers.tasks import replenish_annual_message_quota

        past_due = datetime.now(timezone.utc) - timedelta(hours=1)
        user_id = asyncio.run(_seed_user(
            current_plan="growth", billing_cycle="annual",
            messages_remaining=10, messages_refill_at=past_due,
        ))
        try:
            asyncio.run(engine.dispose())
            with patch("app.database.CeleryAsyncSessionLocal", AsyncSessionLocal), \
                 patch("app.workers.tasks.run_async", side_effect=lambda coro: asyncio.run(coro)):
                replenish_annual_message_quota()

            async def _check():
                await engine.dispose()
                async with AsyncSessionLocal() as db:
                    return await db.get(User, user_id)
            reloaded = asyncio.run(_check())
            assert reloaded.messages_remaining == 10 + PLANS["growth"]["messages"]
            assert reloaded.messages_refill_at > datetime.now(timezone.utc) + timedelta(days=29)
        finally:
            asyncio.run(_cleanup([user_id]))

    def test_replenish_skips_monthly_billing_users(self):
        from app.workers.tasks import replenish_annual_message_quota

        past_due = datetime.now(timezone.utc) - timedelta(hours=1)
        # billing_cycle stays "monthly" (default) even though messages_refill_at
        # is technically set/past — should never happen in practice, but confirms
        # the query filters on billing_cycle, not just the timestamp.
        user_id = asyncio.run(_seed_user(
            current_plan="growth", messages_remaining=10, messages_refill_at=past_due,
        ))
        try:
            asyncio.run(engine.dispose())
            with patch("app.database.CeleryAsyncSessionLocal", AsyncSessionLocal), \
                 patch("app.workers.tasks.run_async", side_effect=lambda coro: asyncio.run(coro)):
                replenish_annual_message_quota()

            async def _check():
                await engine.dispose()
                async with AsyncSessionLocal() as db:
                    return await db.get(User, user_id)
            reloaded = asyncio.run(_check())
            assert reloaded.messages_remaining == 10  # untouched
        finally:
            asyncio.run(_cleanup([user_id]))


class TestReferrals:
    def test_generate_referral_code_charset_and_length(self):
        code = generate_referral_code()
        assert len(code) == 6
        assert code.isalnum() and code.isupper()
        for ambiguous in "0O1IL":
            assert ambiguous not in code

    @pytest.mark.asyncio
    async def test_register_generates_unique_referral_code(self):
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            email = f"{uuid.uuid4()}@test.com"
            resp = await client.post("/api/v1/auth/register", json={
                "email": email, "password": "TestPass123!", "business_name": "Referral Test",
            })
        assert resp.status_code == 201

        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(User).where(User.email == email))
                user = result.scalar_one()
                assert user.referral_code is not None
                assert len(user.referral_code) == 6
                assert user.referred_by_id is None
        finally:
            await _cleanup([user.id])

    @pytest.mark.asyncio
    async def test_register_with_valid_ref_sets_referred_by(self):
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        referrer_id = await _seed_user(referral_code="TESTR1")
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                email = f"{uuid.uuid4()}@test.com"
                resp = await client.post("/api/v1/auth/register", json={
                    "email": email, "password": "TestPass123!", "business_name": "Referred Test",
                    "ref": "testr1",  # minúsculas — debe normalizar a mayúsculas
                })
            assert resp.status_code == 201

            async with AsyncSessionLocal() as db:
                result = await db.execute(select(User).where(User.email == email))
                referred = result.scalar_one()
                assert referred.referred_by_id == referrer_id
        finally:
            await _cleanup([referrer_id, referred.id])

    @pytest.mark.asyncio
    async def test_register_with_invalid_ref_does_not_fail(self):
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            email = f"{uuid.uuid4()}@test.com"
            resp = await client.post("/api/v1/auth/register", json={
                "email": email, "password": "TestPass123!", "business_name": "No Ref Test",
                "ref": "NOTREAL",
            })
        assert resp.status_code == 201

        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(User).where(User.email == email))
                user = result.scalar_one()
                assert user.referred_by_id is None
        finally:
            await _cleanup([user.id])

    @pytest.mark.asyncio
    async def test_reward_referral_credits_both_and_marks_rewarded(self):
        from app.api.v1.webhooks_pkg.stripe import _reward_referral

        referrer_id = await _seed_user(stripe_customer_id="cus_referrer")
        referred_id = await _seed_user(referred_by_id=referrer_id, stripe_customer_id="cus_referred")
        try:
            async with AsyncSessionLocal() as db:
                referred = await db.get(User, referred_id)
                with patch("stripe.Customer.create_balance_transaction") as mock_credit:
                    await _reward_referral(db, referred, amount_total_cents=34900)

            assert mock_credit.call_count == 2
            credited_customers = {c.args[0] for c in mock_credit.call_args_list}
            assert credited_customers == {"cus_referrer", "cus_referred"}
            for call in mock_credit.call_args_list:
                assert call.kwargs["amount"] == -34900
                assert call.kwargs["currency"] == "usd"

            async with AsyncSessionLocal() as db:
                reloaded = await db.get(User, referred_id)
                assert reloaded.referral_rewarded is True
        finally:
            await _cleanup([referrer_id, referred_id])

    @pytest.mark.asyncio
    async def test_reward_referral_is_noop_when_already_rewarded(self):
        from app.api.v1.webhooks_pkg.stripe import _reward_referral

        referrer_id = await _seed_user(stripe_customer_id="cus_referrer")
        referred_id = await _seed_user(
            referred_by_id=referrer_id, stripe_customer_id="cus_referred", referral_rewarded=True,
        )
        try:
            async with AsyncSessionLocal() as db:
                referred = await db.get(User, referred_id)
                with patch("stripe.Customer.create_balance_transaction") as mock_credit:
                    await _reward_referral(db, referred, amount_total_cents=34900)
            mock_credit.assert_not_called()
        finally:
            await _cleanup([referrer_id, referred_id])

    @pytest.mark.asyncio
    async def test_reward_referral_is_noop_without_referrer(self):
        from app.api.v1.webhooks_pkg.stripe import _reward_referral

        user_id = await _seed_user(stripe_customer_id="cus_solo")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with patch("stripe.Customer.create_balance_transaction") as mock_credit:
                    await _reward_referral(db, user, amount_total_cents=34900)
            mock_credit.assert_not_called()
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_reward_referral_skips_credit_but_marks_rewarded_when_referrer_has_no_stripe_customer(self):
        from app.api.v1.webhooks_pkg.stripe import _reward_referral

        referrer_id = await _seed_user()  # sin stripe_customer_id
        referred_id = await _seed_user(referred_by_id=referrer_id, stripe_customer_id="cus_referred")
        try:
            async with AsyncSessionLocal() as db:
                referred = await db.get(User, referred_id)
                with patch("stripe.Customer.create_balance_transaction") as mock_credit:
                    await _reward_referral(db, referred, amount_total_cents=34900)
            mock_credit.assert_called_once_with(
                "cus_referred", amount=-34900, currency="usd",
                description="Recompensa por referido — 1 mes gratis (IARadio)",
            )
            async with AsyncSessionLocal() as db:
                reloaded = await db.get(User, referred_id)
                assert reloaded.referral_rewarded is True
        finally:
            await _cleanup([referrer_id, referred_id])

    @pytest.mark.asyncio
    async def test_referral_stats_endpoint(self):
        from app.api.v1.profile import get_referral_stats

        referrer_id = await _seed_user(referral_code="STATS1")
        referred_ids = [
            await _seed_user(referred_by_id=referrer_id),
            await _seed_user(referred_by_id=referrer_id, referral_rewarded=True),
        ]
        try:
            async with AsyncSessionLocal() as db:
                referrer = await db.get(User, referrer_id)
                out = await get_referral_stats(db=db, current_user=referrer)
            assert out == {"code": "STATS1", "referred_count": 2, "paying_referrals": 1}
        finally:
            await _cleanup([referrer_id] + referred_ids)
