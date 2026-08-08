"""Real-DB integration tests for products.py — zero coverage existed before
this file. Covers CRUD ownership scoping, 404s, and photo upload (MIME
whitelist, size limit, storage_service.upload_bytes mocked so tests never
touch real R2)."""
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.api.v1.products import (
    ProductCreate,
    ProductUpdate,
    create_product,
    delete_product,
    list_products,
    update_product,
    upload_product_photo,
)
from app.database import AsyncSessionLocal, engine
from app.models.product import Product
from app.models.user import User


async def _seed_user():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x")
        db.add(user)
        await db.commit()
        return user.id


def _upload(content: bytes, content_type: str, filename: str = "foto.jpg"):
    f = MagicMock()
    f.content_type = content_type
    f.filename = filename
    f.read = AsyncMock(return_value=content)
    return f


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Product).where(Product.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestCreateProduct:
    @pytest.mark.asyncio
    async def test_creates_product(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_product(
                    body=ProductCreate(name="Pizza Margarita", price=Decimal("120.00"), category="Comida"),
                    db=db, current_user=user,
                )
            assert created.name == "Pizza Margarita"
            assert created.price == Decimal("120.00")
            assert created.active is True
            assert created.photo_url is None
        finally:
            await _cleanup([user_id])


class TestListProducts:
    @pytest.mark.asyncio
    async def test_only_returns_own_products(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                await create_product(body=ProductCreate(name="Mío"), db=db, current_user=owner)
                other = await db.get(User, other_id)
                await create_product(body=ProductCreate(name="Ajeno"), db=db, current_user=other)

            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                products = await list_products(db=db, current_user=owner)
            assert [p.name for p in products] == ["Mío"]
        finally:
            await _cleanup([owner_id, other_id])

    @pytest.mark.asyncio
    async def test_includes_inactive_products(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await create_product(body=ProductCreate(name="Inactivo", active=False), db=db, current_user=user)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                products = await list_products(db=db, current_user=user)
            assert len(products) == 1
            assert products[0].active is False
        finally:
            await _cleanup([user_id])


class TestUpdateProduct:
    @pytest.mark.asyncio
    async def test_updates_fields(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_product(body=ProductCreate(name="Original", price=Decimal("50")), db=db, current_user=user)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                updated = await update_product(
                    product_id=created.id, body=ProductUpdate(name="Editado", active=False),
                    db=db, current_user=user,
                )
            assert updated.name == "Editado"
            assert updated.active is False
            assert updated.price == Decimal("50")  # untouched field preserved
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_cannot_update_another_advertisers_product(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                created = await create_product(body=ProductCreate(name="Owner's"), db=db, current_user=owner)

            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc_info:
                    await update_product(product_id=created.id, body=ProductUpdate(name="Hackeado"), db=db, current_user=other)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([owner_id, other_id])

    @pytest.mark.asyncio
    async def test_unknown_product_returns_404(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await update_product(product_id=uuid.uuid4(), body=ProductUpdate(name="X"), db=db, current_user=user)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])


class TestDeleteProduct:
    @pytest.mark.asyncio
    async def test_deletes_and_disappears_from_list(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_product(body=ProductCreate(name="Temp"), db=db, current_user=user)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await delete_product(product_id=created.id, db=db, current_user=user)
                remaining = await list_products(db=db, current_user=user)
            assert remaining == []
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_cannot_delete_another_advertisers_product(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                created = await create_product(body=ProductCreate(name="Owner's"), db=db, current_user=owner)

            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc_info:
                    await delete_product(product_id=created.id, db=db, current_user=other)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([owner_id, other_id])


class TestUploadProductPhoto:
    @pytest.mark.asyncio
    async def test_rejects_unsupported_mime_type(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_product(body=ProductCreate(name="Con foto"), db=db, current_user=user)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await upload_product_photo(
                        product_id=created.id, file=_upload(b"x", "application/pdf"),
                        db=db, current_user=user,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_rejects_file_over_5mb(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_product(body=ProductCreate(name="Con foto"), db=db, current_user=user)

            oversized = b"x" * (5 * 1024 * 1024 + 1)
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await upload_product_photo(
                        product_id=created.id, file=_upload(oversized, "image/jpeg"),
                        db=db, current_user=user,
                    )
                assert exc_info.value.status_code == 413
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_uploads_and_sets_photo_url(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_product(body=ProductCreate(name="Con foto"), db=db, current_user=user)

            with patch("app.api.v1.products.upload_bytes", new=AsyncMock(return_value="https://cdn.example.com/products/foo.jpg")):
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    updated = await upload_product_photo(
                        product_id=created.id, file=_upload(b"imgbytes", "image/jpeg"),
                        db=db, current_user=user,
                    )
            assert updated.photo_url == "https://cdn.example.com/products/foo.jpg"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_unknown_product_returns_404(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await upload_product_photo(
                        product_id=uuid.uuid4(), file=_upload(b"x", "image/jpeg"),
                        db=db, current_user=user,
                    )
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])
