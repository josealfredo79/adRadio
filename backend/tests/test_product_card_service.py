"""Tests for extract_product_cards — built 2026-08-13 after confirming the
widget/demo-chat frontends render bot replies via `.textContent` (plain
text), so a product link in the reply text is neither clickable nor shown
with a photo unless the backend resolves it into structured card data for
the frontend to render explicitly."""
import uuid

import pytest
from sqlalchemy import delete

from app.database import AsyncSessionLocal, engine
from app.models.product import Product
from app.models.user import User
from app.services.product_card_service import extract_product_cards


async def _seed_user_and_product(**product_overrides):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x")
        db.add(user)
        await db.flush()
        overrides = {"name": "Taco al pastor", "price": 25, "active": True, **product_overrides}
        product = Product(advertiser_id=user.id, **overrides)
        db.add(product)
        await db.commit()
        return user.id, product.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Product).where(Product.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


class TestExtractProductCards:
    @pytest.mark.asyncio
    async def test_no_links_returns_empty_list(self):
        async with AsyncSessionLocal() as db:
            out = await extract_product_cards("Hola, ¿en qué te ayudo?", db)
        assert out == []

    @pytest.mark.asyncio
    async def test_real_link_resolves_to_a_card(self):
        user_id, product_id = await _seed_user_and_product(photo_url="https://x/taco.jpg")
        try:
            text = f"Aquí tienes: https://www.iaradio.online/p/{user_id}/{product_id}"
            async with AsyncSessionLocal() as db:
                out = await extract_product_cards(text, db)
            assert len(out) == 1
            assert out[0]["name"] == "Taco al pastor"
            assert out[0]["photo_url"] == "https://x/taco.jpg"
            assert out[0]["price"] == "$25.00"
            assert out[0]["url"] == f"/p/{user_id}/{product_id}"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_inactive_product_link_is_skipped(self):
        user_id, product_id = await _seed_user_and_product(active=False)
        try:
            text = f"https://www.iaradio.online/p/{user_id}/{product_id}"
            async with AsyncSessionLocal() as db:
                out = await extract_product_cards(text, db)
            assert out == []
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_unresolvable_uuid_pair_does_not_raise(self):
        await engine.dispose()
        text = f"https://www.iaradio.online/p/{uuid.uuid4()}/{uuid.uuid4()}"
        async with AsyncSessionLocal() as db:
            out = await extract_product_cards(text, db)
        assert out == []
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_multiple_links_resolve_in_order_deduplicated(self):
        user_id, product_id = await _seed_user_and_product()
        try:
            text = (
                f"- https://www.iaradio.online/p/{user_id}/{product_id}\n"
                f"- https://www.iaradio.online/p/{user_id}/{product_id}\n"  # duplicate link
            )
            async with AsyncSessionLocal() as db:
                out = await extract_product_cards(text, db)
            assert len(out) == 1  # deduplicated, not two identical cards
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_no_price_renders_as_none(self):
        user_id, product_id = await _seed_user_and_product(price=None)
        try:
            text = f"https://www.iaradio.online/p/{user_id}/{product_id}"
            async with AsyncSessionLocal() as db:
                out = await extract_product_cards(text, db)
            assert out[0]["price"] is None
        finally:
            await _cleanup([user_id])
