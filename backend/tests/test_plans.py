"""Rediseño de planes 2026-10-01 (app/core/plans.py): catálogo, límites por
plan, cuota de conversaciones del bot con modo económico (plan_usage.py),
paquetes extra (Stripe) y los nuevos candados (banners, automatizaciones,
usuarios del equipo)."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.core.plans import ADDONS, FOUNDER_PRICES, PLANS, plan_limit, plan_name
from app.database import AsyncSessionLocal, engine
from app.models.team_member import TeamMember
from app.models.transaction import Transaction
from app.models.user import User
from app.services import plan_usage


class FakeRedis:
    """Lo mínimo de redis.set(nx=True) para la ventana de 24 h."""

    def __init__(self):
        self.keys: set[str] = set()

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.keys:
            return None
        self.keys.add(key)
        return True


class TestCatalog:
    def test_four_sellable_plans_with_new_names(self):
        sellable = {k: p["name"] for k, p in PLANS.items() if p["sellable"]}
        assert sellable == {"starter": "Arranque", "growth": "Negocio", "pro": "Crecimiento", "enterprise": "Empresa"}

    def test_prices_and_quotas_grow_with_the_plan(self):
        order = ["starter", "growth", "pro", "enterprise"]
        prices = [PLANS[k]["price_mxn"] for k in order]
        assert prices == [449, 899, 1799, 4999]
        assert [PLANS[k]["conversations"] for k in order[:3]] == [300, 1000, 3000]
        assert PLANS["enterprise"]["conversations"] == -1

    def test_retired_plans_still_resolve_for_old_users(self):
        assert PLANS["micro"]["sellable"] is False and PLANS["business"]["sellable"] is False
        assert plan_limit("micro", "conversations") > 0

    def test_founder_is_about_30_percent_off(self):
        for key, fp in FOUNDER_PRICES.items():
            discount = 1 - fp["price_mxn"] / PLANS[key]["price_mxn"]
            assert 0.25 <= discount <= 0.35

    def test_trial_is_15_days(self):
        from app.core.plans import TRIAL_DAYS
        assert TRIAL_DAYS == 15

    def test_trial_gets_arranque_limits_plus_radio_taste(self):
        assert plan_limit("trial", "conversations") == plan_limit("starter", "conversations")
        assert plan_limit(None, "radio") == 3
        assert plan_name("trial") == "Prueba gratis" and plan_name("growth") == "Negocio"

    def test_addons(self):
        assert ADDONS["conversations_500"]["conversations"] == 500
        assert ADDONS["messages_500"]["messages"] == 500


async def _seed(**kw):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        u = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Barbería", **kw)
        db.add(u)
        await db.commit()
        return u.id


async def _cleanup(*ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(TeamMember).where(TeamMember.owner_id.in_(ids)))
        await db.execute(delete(Transaction).where(Transaction.advertiser_id.in_(ids)))
        await db.execute(delete(User).where(User.id.in_(ids)))
        await db.commit()
    await engine.dispose()


class TestConversationQuota:
    @pytest.mark.asyncio
    async def test_counts_once_per_customer_per_24h(self):
        uid = await _seed(current_plan="growth")
        try:
            redis = FakeRedis()
            for _ in range(3):
                usage = await plan_usage.register_bot_conversation(uid, "contact-a", redis)
            assert usage.used == 1
            usage = await plan_usage.register_bot_conversation(uid, "contact-b", redis)
            assert usage.used == 2 and usage.cap == 1000 and usage.economy is False
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_economy_mode_after_the_limit_never_a_shutdown(self):
        uid = await _seed(current_plan="starter", bot_conv_month=plan_usage._current_month(), bot_conv_used=299)
        try:
            with patch("app.core.email.send_plan_usage_email", AsyncMock(return_value=True)):
                at_limit = await plan_usage.register_bot_conversation(uid, "c-300", FakeRedis())
                over = await plan_usage.register_bot_conversation(uid, "c-301", FakeRedis())
            assert (at_limit.used, at_limit.economy) == (300, False)
            assert (over.used, over.economy) == (301, True)
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_extra_packs_extend_the_cap(self):
        uid = await _seed(current_plan="starter", bot_conv_month=plan_usage._current_month(),
                          bot_conv_used=300, bot_conv_extra=500)
        try:
            usage = await plan_usage.register_bot_conversation(uid, "c", FakeRedis())
            assert usage.cap == 800 and usage.economy is False
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_new_month_resets_and_spends_only_used_extra(self):
        # Mes anterior: usó 350 de 300 → gastó 50 de sus 500 extra; le quedan 450.
        uid = await _seed(current_plan="starter", bot_conv_month="2026-09", bot_conv_used=350,
                          bot_conv_extra=500, bot_conv_alert=100)
        try:
            usage = await plan_usage.register_bot_conversation(uid, "c", FakeRedis())
            async with AsyncSessionLocal() as db:
                u = await db.get(User, uid)
            assert usage.used == 1 and u.bot_conv_extra == 450 and u.bot_conv_alert == 0
            assert usage.cap == 750
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_alerts_at_80_and_100_percent_once_each(self):
        uid = await _seed(current_plan="starter", bot_conv_month=plan_usage._current_month(), bot_conv_used=238)
        try:
            with patch("app.core.email.send_plan_usage_email", AsyncMock(return_value=True)) as email:
                for i in range(70):  # 239 → 308
                    await plan_usage.register_bot_conversation(uid, f"c{i}", FakeRedis())
                import asyncio
                await asyncio.sleep(0)
            levels = [call.args[4] for call in email.await_args_list]
            assert levels == [80, 100]
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_enterprise_is_unlimited(self):
        uid = await _seed(current_plan="enterprise", bot_conv_month=plan_usage._current_month(), bot_conv_used=50_000)
        try:
            usage = await plan_usage.register_bot_conversation(uid, "c", FakeRedis())
            assert usage.cap == -1 and usage.economy is False
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_failure_never_blocks_the_bot(self):
        with patch("app.database.AsyncSessionLocal", side_effect=RuntimeError("db down")):
            usage = await plan_usage.register_bot_conversation(uuid.uuid4(), "c", None)
        assert usage.economy is False


class TestEconomyRouting:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("economy,first", [(False, "groq"), (True, "openrouter")])
    async def test_provider_order(self, economy, first):
        from app.services import llm_client

        calls = []

        async def fake(client, model, *a, **k):
            calls.append(client)
            return "ok"

        with patch.object(llm_client, "is_groq_configured", return_value=True), \
             patch.object(llm_client, "is_openrouter_configured", return_value=True), \
             patch.object(llm_client, "_get_groq_client", return_value="groq"), \
             patch.object(llm_client, "_get_openrouter_client", return_value="openrouter"), \
             patch.object(llm_client, "_openai_compatible_completion", side_effect=fake):
            assert await llm_client.chat_completion([{"role": "user", "content": "hola"}], economy=economy) == "ok"
        assert calls == [first]

    @pytest.mark.asyncio
    async def test_rag_counts_only_when_the_ai_is_called_and_passes_economy(self):
        from app.services import rag_service

        user = User(id=uuid.uuid4(), email="x@test.com", password_hash="x", bot_instructions="Abrimos 10 a 20 h")
        usage = plan_usage.ConversationUsage(used=301, cap=300, economy=True)
        with patch.object(rag_service, "_fetch_user", AsyncMock(return_value=user)), \
             patch.object(rag_service, "get_embedding", AsyncMock(side_effect=RuntimeError("sin embeddings"))), \
             patch("app.services.plan_usage.register_bot_conversation", AsyncMock(return_value=usage)) as reg, \
             patch.object(rag_service, "generate_bot_response", AsyncMock(return_value="respuesta")) as gen:
            out = await rag_service.answer_with_rag(
                advertiser_id=str(user.id), query="¿horario?", conversation_history=[], db=AsyncMock(),
                conversation_key="contact-1", redis=None,
            )
        assert out == "respuesta"
        reg.assert_awaited_once()
        assert gen.await_args.kwargs["economy"] is True

    @pytest.mark.asyncio
    async def test_canned_greeting_costs_nothing_and_is_not_counted(self):
        from app.services import rag_service

        user = User(id=uuid.uuid4(), email="x@test.com", password_hash="x", business_name="Barbería")
        with patch.object(rag_service, "_fetch_user", AsyncMock(return_value=user)), \
             patch.object(rag_service, "get_embedding", AsyncMock(side_effect=RuntimeError("sin embeddings"))), \
             patch("app.services.plan_usage.register_bot_conversation", AsyncMock()) as reg:
            await rag_service.answer_with_rag(
                advertiser_id=str(user.id), query="hola", conversation_history=[], db=AsyncMock(),
                conversation_key="contact-1", redis=None,
            )
        reg.assert_not_awaited()


class TestAddonsAndUsage:
    @pytest.mark.asyncio
    async def test_addon_credits_conversations_and_messages(self):
        from app.api.v1.webhooks_pkg.stripe import _apply_addon

        uid = await _seed(current_plan="growth", stripe_customer_id=f"cus_{uuid.uuid4().hex[:10]}",
                          messages_remaining=10)
        try:
            async with AsyncSessionLocal() as db:
                cust = (await db.get(User, uid)).stripe_customer_id
            async with AsyncSessionLocal() as db:
                await _apply_addon(db, cust, "conversations_500", f"pi_{uuid.uuid4().hex}", 900, "usd")
            async with AsyncSessionLocal() as db:
                await _apply_addon(db, cust, "messages_500", f"pi_{uuid.uuid4().hex}", 600, "usd")
            async with AsyncSessionLocal() as db:
                u = await db.get(User, uid)
            assert u.bot_conv_extra == 500 and u.messages_remaining == 510
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_usage_endpoint(self):
        from app.api.v1.payments import plan_usage as usage_endpoint

        uid = await _seed(current_plan="growth", bot_conv_month=plan_usage._current_month(),
                          bot_conv_used=120, bot_conv_extra=500, messages_remaining=480)
        try:
            async with AsyncSessionLocal() as db:
                u = await db.get(User, uid)
            out = await usage_endpoint(current_user=u)
            assert out["plan_name"] == "Negocio"
            assert out["conversations"] == {"used": 120, "limit": 1000, "extra": 500, "cap": 1500, "economy": False}
            assert out["messages_remaining"] == 480 and out["radio_limit"] == 4 and out["team_limit"] == 2
        finally:
            await _cleanup(uid)

    @pytest.mark.asyncio
    async def test_checkout_rejects_retired_plans(self):
        from app.api.v1.payments import CheckoutSessionBody, create_checkout_session

        uid = await _seed(current_plan="trial")
        try:
            async with AsyncSessionLocal() as db:
                u = await db.get(User, uid)
                with pytest.raises(HTTPException) as exc:
                    await create_checkout_session(
                        request=AsyncMock(), body=CheckoutSessionBody(plan="micro"),
                        current_user=u, db=db, _=None, redis=None,
                    )
            assert exc.value.status_code == 400
        finally:
            await _cleanup(uid)


class TestNewGates:
    @pytest.mark.asyncio
    async def test_team_seats_per_plan(self):
        from app.api.v1.team import TeamMemberInvite, invite_member

        starter = await _seed(current_plan="starter")
        growth = await _seed(current_plan="growth")
        try:
            async with AsyncSessionLocal() as db:
                u = await db.get(User, starter)
                with pytest.raises(HTTPException) as exc:
                    await invite_member(body=TeamMemberInvite(email="a@test.com"), db=db, current_user=u)
            assert exc.value.status_code == 402
            async with AsyncSessionLocal() as db:
                u = await db.get(User, growth)
                await invite_member(body=TeamMemberInvite(email="a@test.com"), db=db, current_user=u)
            async with AsyncSessionLocal() as db:
                u = await db.get(User, growth)
                with pytest.raises(HTTPException) as exc:
                    await invite_member(body=TeamMemberInvite(email="b@test.com"), db=db, current_user=u)
            assert exc.value.status_code == 402
        finally:
            await _cleanup(starter, growth)

    @pytest.mark.asyncio
    async def test_automations_and_banners_start_at_negocio(self):
        from app.api.v1.automations import FlowCreate, create_flow
        from app.api.v1.campaigns import GenerateImageRequest, generate_image

        uid = await _seed(current_plan="starter")
        try:
            async with AsyncSessionLocal() as db:
                u = await db.get(User, uid)
                with pytest.raises(HTTPException) as exc:
                    await create_flow(body=FlowCreate(name="Bienvenida"), db=db, current_user=u)
                assert exc.value.status_code == 402 and "Negocio" in exc.value.detail
                with pytest.raises(HTTPException) as exc:
                    await generate_image(
                        body=GenerateImageRequest(campaign_name="x", message_text="y", business_name="z"),
                        current_user=u,
                    )
                assert exc.value.status_code == 402
        finally:
            await _cleanup(uid)


class TestSalesBotIntent:
    @pytest.mark.parametrize("text,expected", [
        ("quiero el plan arranque", "starter"),
        ("me interesa contratar el plan crecimiento", "pro"),
        ("quiero ver el crecimiento de mi negocio", None),
        ("¿cuánto cuesta el pastel?", None),
    ])
    def test_new_plan_names(self, text, expected):
        from app.services.claude_service import detect_plan_purchase_intent

        assert detect_plan_purchase_intent(text) == expected
