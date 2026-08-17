"""Real-DB tests for the AdRadio-hosted public landing page endpoint —
GET /api/v1/public/site/{slug}. Mirrors the security pattern already
covered for widget_preview in test_widget_endpoints.py::TestWidgetPreview."""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from starlette.requests import Request

from app.api.v1.public_site import (
    get_public_product_by_advertiser,
    get_public_site,
    get_public_site_product,
    get_public_site_products,
    get_public_site_stories,
)
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.customer_story import CustomerStory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.user import User


def _request() -> Request:
    scope = {
        "type": "http", "method": "GET", "path": "/api/v1/public/site/x", "headers": [],
        "client": (f"test-{uuid.uuid4()}", 123), "query_string": b"",
    }
    return Request(scope)


async def _seed_user(**overrides):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", **overrides)
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        order_ids = (
            await db.execute(select(Order.id).where(Order.advertiser_id.in_(user_ids)))
        ).scalars().all()
        if order_ids:
            await db.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
        await db.execute(delete(Order).where(Order.advertiser_id.in_(user_ids)))
        await db.execute(delete(Product).where(Product.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestGetPublicSite:
    @pytest.mark.asyncio
    async def test_unknown_slug_returns_404(self):
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc_info:
                await get_public_site(request=_request(), slug="no-existe", db=db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_null_slug_is_not_reachable(self):
        user_id = await _seed_user(business_name="Sin slug")
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc_info:
                    await get_public_site(request=_request(), slug="", db=db)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_returns_only_public_safe_fields(self):
        user_id = await _seed_user(
            business_name="Tacos El Primo", business_category="restaurante", city="Tlaxiaco",
            slug="tacos-el-primo", bot_name="Sofia",
        )
        try:
            async with AsyncSessionLocal() as db:
                out = await get_public_site(request=_request(), slug="tacos-el-primo", db=db)
            assert out["advertiser_id"] == str(user_id)
            assert out["business_name"] == "Tacos El Primo"
            assert out["business_category"] == "restaurante"
            assert out["city"] == "Tlaxiaco"
            assert out["agent"] == "Sofia"
            # Default theme/logo/hero when not configured.
            assert out["logo_url"] == ""
            assert out["hero_image_url"] == ""
            assert out["site_theme"] == "medianoche"
            # No WhatsApp number shown when nothing is actually connected.
            assert out["whatsapp_number"] == ""
            # Nothing sensitive (email, tokens, phone) leaks into the public payload.
            assert "email" not in out
            assert "meta_token_cipher" not in out
            assert "phone" not in out
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_logo_and_site_theme_passthrough(self):
        user_id = await _seed_user(
            business_name="Con logo", slug="con-logo",
            logo_url="https://cdn.example.com/logos/foo.jpg",
            hero_image_url="https://cdn.example.com/hero-images/foo.jpg",
            site_theme="claro",
        )
        try:
            async with AsyncSessionLocal() as db:
                out = await get_public_site(request=_request(), slug="con-logo", db=db)
            assert out["logo_url"] == "https://cdn.example.com/logos/foo.jpg"
            assert out["hero_image_url"] == "https://cdn.example.com/hero-images/foo.jpg"
            assert out["site_theme"] == "claro"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_whatsapp_number_only_shown_when_meta_connected(self):
        """The public footer must only ever surface the real, connected Meta
        WhatsApp Business number (meta_display_phone_number) — never
        User.whatsapp_number, which is a different field entirely (the
        owner's personal notification number, not customer-facing)."""
        user_id = await _seed_user(
            business_name="Sin conectar", slug="sin-conectar",
            whatsapp_number="+529531953182",  # personal notification number — must NOT leak
            meta_connection_status="not_connected",
        )
        try:
            async with AsyncSessionLocal() as db:
                out = await get_public_site(request=_request(), slug="sin-conectar", db=db)
            assert out["whatsapp_number"] == ""
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_whatsapp_number_shown_when_meta_connected(self):
        user_id = await _seed_user(
            business_name="Conectado", slug="conectado",
            whatsapp_number="+529531953182",
            meta_connection_status="connected",
            meta_display_phone_number="+52 1 443 786 4292",
        )
        try:
            async with AsyncSessionLocal() as db:
                out = await get_public_site(request=_request(), slug="conectado", db=db)
            assert out["whatsapp_number"] == "+52 1 443 786 4292"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_tagline_passthrough_and_default(self):
        user_id = await _seed_user(business_name="Con tagline", slug="con-tagline", landing_tagline="El mejor sabor de la ciudad")
        user_id2 = await _seed_user(business_name="Sin tagline", slug="sin-tagline")
        try:
            async with AsyncSessionLocal() as db:
                out = await get_public_site(request=_request(), slug="con-tagline", db=db)
            assert out["tagline"] == "El mejor sabor de la ciudad"
            async with AsyncSessionLocal() as db:
                out2 = await get_public_site(request=_request(), slug="sin-tagline", db=db)
            assert out2["tagline"] == ""
        finally:
            await _cleanup([user_id, user_id2])

    @pytest.mark.asyncio
    async def test_slug_lookup_is_case_insensitive(self):
        user_id = await _seed_user(business_name="Tacos", slug="mi-negocio")
        try:
            async with AsyncSessionLocal() as db:
                out = await get_public_site(request=_request(), slug="MI-NEGOCIO", db=db)
            assert out["business_name"] == "Tacos"
        finally:
            await _cleanup([user_id])


class TestGetPublicSiteStories:
    @pytest.mark.asyncio
    async def test_unknown_slug_returns_404(self):
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc_info:
                await get_public_site_stories(request=_request(), slug="no-existe", db=db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_only_returns_approved_stories(self):
        user_id = await _seed_user(business_name="Con historias", slug="con-historias")
        try:
            async with AsyncSessionLocal() as db:
                db.add_all([
                    CustomerStory(
                        advertiser_id=user_id, media_url="https://x/aprobada.mp3",
                        transcription="Excelente servicio", sentiment="positivo", approved=True,
                    ),
                    CustomerStory(
                        advertiser_id=user_id, media_url="https://x/pendiente.mp3",
                        transcription="Aún sin aprobar", sentiment="positivo", approved=False,
                    ),
                ])
                await db.commit()

            async with AsyncSessionLocal() as db:
                out = await get_public_site_stories(request=_request(), slug="con-historias", db=db)
            assert len(out) == 1
            assert out[0]["transcription"] == "Excelente servicio"
            assert out[0]["media_url"] == "https://x/aprobada.mp3"
            assert out[0]["sentiment"] == "positivo"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_never_leaks_another_advertisers_stories(self):
        user_id = await _seed_user(business_name="A", slug="dueno-a-stories")
        other_id = await _seed_user(business_name="B", slug="dueno-b-stories")
        try:
            async with AsyncSessionLocal() as db:
                db.add(CustomerStory(
                    advertiser_id=other_id, media_url="https://x/ajena.mp3",
                    transcription="No es mía", sentiment="positivo", approved=True,
                ))
                await db.commit()

            async with AsyncSessionLocal() as db:
                out = await get_public_site_stories(request=_request(), slug="dueno-a-stories", db=db)
            assert out == []
        finally:
            await _cleanup([user_id, other_id])

    @pytest.mark.asyncio
    async def test_only_exposes_first_name_of_contact(self):
        user_id = await _seed_user(business_name="Con contacto", slug="con-contacto-story")
        try:
            async with AsyncSessionLocal() as db:
                contact = Contact(advertiser_id=user_id, name="Laura Gómez Hernández", phone="+529531953182")
                db.add(contact)
                await db.flush()
                db.add(CustomerStory(
                    advertiser_id=user_id, contact_id=contact.id, media_url="https://x/laura.mp3",
                    transcription="Muy contenta", sentiment="positivo", approved=True,
                ))
                await db.commit()

            async with AsyncSessionLocal() as db:
                out = await get_public_site_stories(request=_request(), slug="con-contacto-story", db=db)
            assert out[0]["contact_name"] == "Laura"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_limits_to_6_most_recent(self):
        user_id = await _seed_user(business_name="Muchas historias", slug="muchas-historias")
        try:
            async with AsyncSessionLocal() as db:
                db.add_all([
                    CustomerStory(
                        advertiser_id=user_id, media_url=f"https://x/{i}.mp3",
                        transcription=f"Historia {i}", sentiment="positivo", approved=True,
                    )
                    for i in range(8)
                ])
                await db.commit()

            async with AsyncSessionLocal() as db:
                out = await get_public_site_stories(request=_request(), slug="muchas-historias", db=db)
            assert len(out) == 6
        finally:
            await _cleanup([user_id])


class TestGetPublicSiteProducts:
    @pytest.mark.asyncio
    async def test_unknown_slug_returns_404(self):
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc_info:
                await get_public_site_products(request=_request(), slug="no-existe", db=db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_only_returns_active_products(self):
        user_id = await _seed_user(business_name="Tacos", slug="con-catalogo")
        try:
            async with AsyncSessionLocal() as db:
                db.add(Product(advertiser_id=user_id, name="Taco al pastor", price=25, active=True))
                db.add(Product(advertiser_id=user_id, name="Descontinuado", price=10, active=False))
                await db.commit()

            async with AsyncSessionLocal() as db:
                out = await get_public_site_products(request=_request(), slug="con-catalogo", db=db)
            assert [p["name"] for p in out] == ["Taco al pastor"]
            assert out[0]["price"] == "25.00"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_never_leaks_other_advertisers_products(self):
        user_id = await _seed_user(business_name="A", slug="negocio-a")
        other_id = await _seed_user(business_name="B", slug="negocio-b")
        try:
            async with AsyncSessionLocal() as db:
                db.add(Product(advertiser_id=other_id, name="Ajeno", active=True))
                await db.commit()

            async with AsyncSessionLocal() as db:
                out = await get_public_site_products(request=_request(), slug="negocio-a", db=db)
            assert out == []
        finally:
            await _cleanup([user_id, other_id])

    @pytest.mark.asyncio
    async def test_sales_count_only_counts_confirmed_orders(self):
        user_id = await _seed_user(business_name="Tacos", slug="con-ventas")
        try:
            async with AsyncSessionLocal() as db:
                product = Product(advertiser_id=user_id, name="Taco al pastor", price=25, active=True)
                db.add(product)
                await db.flush()

                confirmed_order = Order(
                    advertiser_id=user_id, items_raw="2 tacos", state="confirmed", order_number=1,
                )
                cancelled_order = Order(
                    advertiser_id=user_id, items_raw="1 taco", state="cancelled", order_number=2,
                )
                db.add_all([confirmed_order, cancelled_order])
                await db.flush()

                db.add_all([
                    OrderItem(order_id=confirmed_order.id, product_id=product.id, product_name_snapshot=product.name, quantity=2),
                    OrderItem(order_id=cancelled_order.id, product_id=product.id, product_name_snapshot=product.name, quantity=1),
                ])
                await db.commit()

            async with AsyncSessionLocal() as db:
                out = await get_public_site_products(request=_request(), slug="con-ventas", db=db)
            assert len(out) == 1
            assert out[0]["sales_count"] == 1  # counts confirmed OrderItem rows, not cancelled, not summed quantity
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_sales_count_defaults_to_zero_with_no_orders(self):
        user_id = await _seed_user(business_name="Tacos", slug="sin-ventas")
        try:
            async with AsyncSessionLocal() as db:
                db.add(Product(advertiser_id=user_id, name="Taco al pastor", price=25, active=True))
                await db.commit()

            async with AsyncSessionLocal() as db:
                out = await get_public_site_products(request=_request(), slug="sin-ventas", db=db)
            assert out[0]["sales_count"] == 0
        finally:
            await _cleanup([user_id])


class TestGetPublicSiteProduct:
    """GET /api/v1/public/site/{slug}/products/{product_id} — the individual
    shareable product page's data source, built 2026-08-13."""

    @pytest.mark.asyncio
    async def test_unknown_slug_returns_404(self):
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc_info:
                await get_public_site_product(
                    request=_request(), slug="no-existe", product_id=uuid.uuid4(), db=db,
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_unknown_product_id_returns_404(self):
        user_id = await _seed_user(business_name="Tacos", slug="sin-ese-producto")
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc_info:
                    await get_public_site_product(
                        request=_request(), slug="sin-ese-producto", product_id=uuid.uuid4(), db=db,
                    )
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_inactive_product_returns_404(self):
        user_id = await _seed_user(business_name="Tacos", slug="inactivo")
        try:
            async with AsyncSessionLocal() as db:
                product = Product(advertiser_id=user_id, name="Descontinuado", price=10, active=False)
                db.add(product)
                await db.commit()
                product_id = product.id

            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc_info:
                    await get_public_site_product(request=_request(), slug="inactivo", product_id=product_id, db=db)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_never_leaks_another_advertisers_product(self):
        user_id = await _seed_user(business_name="A", slug="dueno-a")
        other_id = await _seed_user(business_name="B", slug="dueno-b")
        try:
            async with AsyncSessionLocal() as db:
                product = Product(advertiser_id=other_id, name="Ajeno", price=99, active=True)
                db.add(product)
                await db.commit()
                product_id = product.id

            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc_info:
                    await get_public_site_product(request=_request(), slug="dueno-a", product_id=product_id, db=db)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id, other_id])

    @pytest.mark.asyncio
    async def test_returns_full_detail_with_business_name(self):
        user_id = await _seed_user(
            business_name="Tacos El Primo", slug="tacos-detalle",
            meta_connection_status="connected", meta_display_phone_number="+52 1 443 786 4292",
        )
        try:
            async with AsyncSessionLocal() as db:
                product = Product(
                    advertiser_id=user_id, name="Taco al pastor", description="Con piña",
                    price=25, category="Tacos", photo_url="https://x/taco.jpg", active=True,
                )
                db.add(product)
                await db.commit()
                product_id = product.id

            async with AsyncSessionLocal() as db:
                out = await get_public_site_product(request=_request(), slug="tacos-detalle", product_id=product_id, db=db)
            assert out["name"] == "Taco al pastor"
            assert out["description"] == "Con piña"
            assert out["price"] == "25.00"
            assert out["photo_url"] == "https://x/taco.jpg"
            assert out["business_name"] == "Tacos El Primo"
            assert out["slug"] == "tacos-detalle"
            assert out["sales_count"] == 0
            assert out["whatsapp_number"] == "+52 1 443 786 4292"
        finally:
            await _cleanup([user_id])


class TestGetPublicProductByAdvertiser:
    """GET /api/v1/public/product/{advertiser_id}/{product_id} — same
    product detail, keyed by advertiser_id instead of slug so it works for
    advertisers who never published a landing page. Built 2026-08-13 to
    back the WhatsApp catalog reply's per-product link."""

    @pytest.mark.asyncio
    async def test_unknown_advertiser_id_returns_404(self):
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc_info:
                await get_public_product_by_advertiser(
                    request=_request(), advertiser_id=uuid.uuid4(), product_id=uuid.uuid4(), db=db,
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_works_without_a_published_slug(self):
        """The whole point of this endpoint — the advertiser has NO slug set
        at all, and it still returns the product correctly."""
        user_id = await _seed_user(business_name="Sin Landing")  # no slug=
        try:
            async with AsyncSessionLocal() as db:
                product = Product(
                    advertiser_id=user_id, name="Corte de cabello", price=150, active=True,
                )
                db.add(product)
                await db.commit()
                product_id = product.id

            async with AsyncSessionLocal() as db:
                out = await get_public_product_by_advertiser(
                    request=_request(), advertiser_id=user_id, product_id=product_id, db=db,
                )
            assert out["name"] == "Corte de cabello"
            assert out["business_name"] == "Sin Landing"
            assert out["slug"] == ""  # no landing page — frontend must handle this gracefully
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_never_leaks_another_advertisers_product(self):
        user_id = await _seed_user(business_name="A")
        other_id = await _seed_user(business_name="B")
        try:
            async with AsyncSessionLocal() as db:
                product = Product(advertiser_id=other_id, name="Ajeno", price=99, active=True)
                db.add(product)
                await db.commit()
                product_id = product.id

            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc_info:
                    await get_public_product_by_advertiser(
                        request=_request(), advertiser_id=user_id, product_id=product_id, db=db,
                    )
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id, other_id])
