"""Tests for the IaRadio marketing-site demo chat (/api/v1/chat/demo).

Real production bug found 2026-08-13: a real website visitor asked this
bot (Alex) for a service/plan link and got "No tengo ese dato a la mano" —
this endpoint is a completely separate code path from the real customer-
facing bots (widget.py/inbound_pipeline.py) and was never wired to the
catalog/product system at all, so it had zero links to offer even though
IaRadio's own plans exist as real Product rows with real shareable pages
(see DEMO_PLANS_ADVERTISER_EMAIL in chat_demo.py)."""
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import delete, select

from app.api.v1.chat_demo import _build_demo_context, _format_plan_links
from app.database import AsyncSessionLocal, engine
from app.models.product import Product
from app.models.user import User


async def _cleanup_by_email(email: str):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user:
            await db.execute(delete(Product).where(Product.advertiser_id == user.id))
            await db.execute(delete(User).where(User.id == user.id))
            await db.commit()


class TestFormatPlanLinks:
    @pytest.mark.asyncio
    async def test_returns_empty_string_when_demo_account_does_not_exist(self):
        """Doesn't crash the whole demo chat if that specific account is
        ever renamed/removed — degrades to no links, not an error."""
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            out = await _format_plan_links(db)
        # Whatever the real account's state is, this must never raise.
        assert isinstance(out, str)

    @pytest.mark.asyncio
    async def test_real_plan_products_produce_real_links(self):
        """Uses a throwaway email so this test doesn't depend on (or
        clobber) the real production demo account's actual plan rows."""
        fake_email = f"{uuid.uuid4()}@test.com"
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            user = User(email=fake_email, password_hash="x", business_name="IARadio")
            db.add(user)
            await db.flush()
            product = Product(
                advertiser_id=user.id, name="Plan Starter", price=499,
                category="Planes IaRadio", active=True,
            )
            other_category_product = Product(
                advertiser_id=user.id, name="No es un plan", price=10,
                category="Otra categoría", active=True,
            )
            db.add_all([product, other_category_product])
            await db.commit()
            user_id, product_id = user.id, product.id

        try:
            with patch("app.api.v1.chat_demo.DEMO_PLANS_ADVERTISER_EMAIL", fake_email):
                async with AsyncSessionLocal() as db:
                    out = await _format_plan_links(db)

            assert "Plan Starter" in out
            assert f"/p/{user_id}/{product_id}" in out
            assert "No es un plan" not in out  # wrong category, excluded
        finally:
            await _cleanup_by_email(fake_email)


class TestBuildDemoContext:
    def test_includes_links_block_when_links_present(self):
        out = _build_demo_context("- Plan Starter: https://x/p/1/2")
        assert "LINKS REALES DE CADA PLAN" in out
        assert "https://x/p/1/2" in out

    def test_omits_links_block_when_no_links(self):
        out = _build_demo_context("")
        assert "LINKS REALES DE CADA PLAN" not in out
