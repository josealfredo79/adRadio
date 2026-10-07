"""WhatsApp manda links, no fotos aparte: el catálogo es UN link a la web y,
si se habla de UN producto, va su link (WhatsApp lo previsualiza con foto en
el mismo mensaje). La página del negocio entrega su portada a la vista previa."""
import uuid

import pytest
from sqlalchemy import delete

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.product import Product
from app.models.user import User
from app.services.catalog_service import format_catalog_whatsapp, handle_catalog_query
from app.services.product_link_service import (
    mentioned_product,
    product_url,
    with_product_link,
)
from app.services.site_photos import cover_photo_url, stock_giro


def _p(name, price=100):
    return Product(id=uuid.uuid4(), advertiser_id=uuid.uuid4(), name=name, price=price, active=True)


def test_whatsapp_catalog_is_one_web_link_with_a_few_highlights():
    user = User(id=uuid.uuid4(), slug="tacos-el-primo")
    products = [_p(f"Taco {i}") for i in range(5)]
    text = format_catalog_whatsapp(products, user)
    assert text.count("http") == 1
    assert f"{settings.BASE_URL}/sitio/tacos-el-primo#catalogo" in text
    assert "Taco 0" in text and "Taco 2" in text and "Taco 3" not in text
    assert "y 2 más" in text


def test_whatsapp_catalog_without_published_page_keeps_the_product_list():
    user = User(id=uuid.uuid4(), slug=None)
    text = format_catalog_whatsapp([_p("Taco"), _p("Agua")], user)
    assert "/p/" in text and "Taco" in text and "Agua" in text


def test_product_link_goes_last_or_first_if_the_reply_already_has_a_link():
    p = _p("Penthouse Roma")
    plain = with_product_link("Tiene 3 recámaras y terraza.", p)
    assert plain.startswith("Tiene") and plain.endswith(product_url(p))
    linked = with_product_link("Más aquí: https://x.example.com/a", p)
    assert linked.startswith("📸") and linked.index(product_url(p)) < linked.index("https://x.example.com")


def test_cover_photo_prefers_owner_photos_then_old_cover_then_stock():
    base = "https://www.iaradio.online"
    assert cover_photo_url(User(site_photos=["https://c/a.jpg"], hero_image_url="https://c/h.jpg"), base) == "https://c/a.jpg"
    assert cover_photo_url(User(site_photos=[], hero_image_url="https://c/h.jpg"), base) == "https://c/h.jpg"
    assert cover_photo_url(User(business_category="Barbería"), base) == f"{base}/stock/belleza/1.jpg"
    assert stock_giro("algo raro") == "otro"


@pytest.mark.asyncio
async def test_mentioned_product_only_when_it_is_one():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x")
        db.add(user)
        await db.flush()
        for name in ("Penthouse Roma Norte", "Casa Coyoacán", "Terreno Tlalpan"):
            db.add(Product(advertiser_id=user.id, name=name, price=1, active=True))
        await db.commit()
        uid = user.id
    try:
        async with AsyncSessionLocal() as db:
            p = await mentioned_product(db, uid, "¿tienes fotos del penthouse roma norte?", "Claro, tiene 3 recámaras.")
            assert p is not None and p.name == "Penthouse Roma Norte"
            # Lo dijo el bot, no el cliente: también cuenta.
            p = await mentioned_product(db, uid, "¿algo con jardín?", "La Casa Coyoacán tiene jardín privado.")
            assert p is not None and p.name == "Casa Coyoacán"
            # Dos productos: no se adivina.
            assert await mentioned_product(db, uid, "casa coyoacán o terreno tlalpan?", "Ambos.") is None
            # Ya trae link de producto: nada.
            assert await mentioned_product(db, uid, "penthouse roma norte", f"Aquí: {settings.BASE_URL}/p/x/y") is None
            # Por WhatsApp, el catálogo sin página publicada sigue siendo la lista.
            user = await db.get(User, uid)
            reply = await handle_catalog_query(db, user, "¿qué venden?", channel="whatsapp")
            assert reply and "Penthouse Roma Norte" in reply
    finally:
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Product).where(Product.advertiser_id == uid))
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()


@pytest.mark.asyncio
async def test_site_page_preview_for_whatsapp_has_the_cover_photo():
    from app.main import _render_site_og_html

    await engine.dispose()
    slug = f"s-{uuid.uuid4().hex[:10]}"
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", slug=slug, business_name="Tacos El Primo",
                    site_photos=["https://cdn.example.com/a.jpg"], landing_tagline="Los mejores de la ciudad")
        db.add(user)
        await db.commit()
        uid = user.id
    try:
        html = await _render_site_og_html(slug, "https://www.iaradio.online")
        assert 'og:image" content="https://cdn.example.com/a.jpg"' in html
        assert 'og:title" content="Tacos El Primo"' in html
        assert await _render_site_og_html("no-existe-" + slug, "https://www.iaradio.online") is None
    finally:
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()


@pytest.mark.asyncio
async def test_bot_sees_the_catalog_when_answering():
    """El bot sabe del producto aunque no esté en la base de conocimiento ni en
    las instrucciones: el catálogo va en su contexto."""
    from unittest.mock import AsyncMock, patch

    from app.services.rag_service import answer_with_rag

    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x")
        db.add(user)
        await db.flush()
        db.add(Product(advertiser_id=user.id, name="Penthouse Roma Norte", price=12900000, category="Venta",
                       description="3 recámaras, 3 baños, terraza privada de 60 m²", active=True))
        db.add(Product(advertiser_id=user.id, name="Oculto", price=1, active=False))
        await db.commit()
        uid = user.id
    try:
        gen = AsyncMock(return_value="Tiene 3 recámaras y terraza de 60 m².")
        with patch("app.services.rag_service.generate_bot_response", gen), \
                patch("app.services.rag_service.get_embedding", AsyncMock(side_effect=Exception("sin embeddings"))):
            async with AsyncSessionLocal() as db:
                await answer_with_rag(advertiser_id=str(uid), query="¿cuántas recámaras tiene el penthouse?",
                                      conversation_history=[], db=db)
        ctx = gen.await_args.kwargs["advertiser_context"]
        assert "Penthouse Roma Norte" in ctx and "$12,900,000.00" in ctx and "terraza privada" in ctx
        assert "Oculto" not in ctx
    finally:
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Product).where(Product.advertiser_id == uid))
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()
