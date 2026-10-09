"""Copiloto, paso 2 (copilot_business_tools.py): citas, pedidos, catálogo y
horario, contra la BD real (mismo patrón que test_copilot_service_actions.py).

Lo crítico: los cambios solo pasan por la confirmación firmada; cambiar un
precio o el horario también corrige lo que dicen las instrucciones del bot;
un nombre que coincide con dos productos no cambia "el que sea"; y solo se
aceptan fotos que subió el propio dueño."""
import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal, engine
from app.models.appointment import Appointment
from app.models.order import Order
from app.models.product import Product
from app.models.user import User
from app.services import copilot_business_tools as biz
from app.services.availability_service import TZ
from app.services.copilot_service import (
    CONFIRM_TOOLS,
    TOOLS,
    _build_system_prompt,
    _execute_confirm_tool,
    _execute_immediate_tool,
    _preview_confirm_tool,
)

INSTRUCTIONS = "Horario: Lunes 10:00–20:00\nServicios y precios:\n- Corte — $150\n- Barba — $100"
WEEK = {d: ["10:00", "20:00"] for d in ("mon", "tue", "wed", "thu", "fri")} | {"sat": ["10:00", "18:00"], "sun": None}


async def _seed_user(**overrides) -> uuid.UUID:
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", **overrides)
        db.add(user)
        await db.commit()
        return user.id


async def _user(db, user_id) -> User:
    return (await db.execute(select(User).where(User.id == user_id))).scalar_one()


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for model in (Appointment, Order, Product):
            await db.execute(delete(model).where(model.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_appointments_today_skip_cancelled_and_other_days():
    user_id = await _seed_user()
    try:
        today = datetime.now(TZ).date()
        at = lambda d, h: datetime.combine(d, time(h, 0), tzinfo=TZ)
        async with AsyncSessionLocal() as db:
            for name, when, status in [
                ("Ana", at(today, 23), "confirmed"),
                ("Beto", at(today, 22), "cancelled"),
                ("Carla", at(today + timedelta(days=1), 10), "pending"),
            ]:
                db.add(Appointment(advertiser_id=user_id, customer_name=name, service="Corte",
                                   scheduled_at=when, status=status))
            await db.commit()
            user = await _user(db, user_id)
            out = await _execute_immediate_tool(db, user, "list_appointments", {})
            assert [a["customer"] for a in out["items"]] == ["Ana"]
            assert out["items"][0]["time"] == "23:00"
            nxt = await _execute_immediate_tool(db, user, "list_appointments", {"date_from": (today + timedelta(days=1)).isoformat()})
            assert [a["customer"] for a in nxt["items"]] == ["Carla"]
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_orders_filter_in_progress_vs_confirmed():
    user_id = await _seed_user()
    try:
        async with AsyncSessionLocal() as db:
            db.add(Order(advertiser_id=user_id, order_number=1, state="confirmed", items_raw="2 pizzas", customer_name="Ana"))
            db.add(Order(advertiser_id=user_id, order_number=2, state="collecting_address", items_raw="1 refresco"))
            await db.commit()
            user = await _user(db, user_id)
            done = await biz.list_orders(db, user, {"state": "confirmed"})
            going = await biz.list_orders(db, user, {"state": "in_progress"})
            everything = await biz.list_orders(db, user, {})
        assert [o["items"] for o in done["items"]] == ["2 pizzas"]
        assert [o["state"] for o in going["items"]] == ["in_progress"]
        assert everything["count"] == 2
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_create_product_waits_for_yes_and_only_takes_own_photos():
    user_id = await _seed_user()
    try:
        assert {"create_product", "update_product", "update_business_hours"} <= CONFIRM_TOOLS
        own = f"https://x/api/v1/radio/audio/products/{user_id}/a.jpg"
        foreign = f"https://x/api/v1/radio/audio/products/{uuid.uuid4()}/b.jpg"
        async with AsyncSessionLocal() as db:
            user = await _user(db, user_id)
            summary, args, err = await _preview_confirm_tool(
                db, user, "create_product", {"name": "Tinte", "price": "$450", "photo_url": own},
            )
            assert err is None and "Tinte" in summary and "$450" in summary and "foto" in summary
            # Nada se guarda en la vista previa.
            assert (await db.execute(select(Product).where(Product.advertiser_id == user_id))).first() is None
            data, err = await _execute_confirm_tool(db, user, "create_product", args)
            assert err is None and data["has_photo"] is True
            _, other, _ = await _preview_confirm_tool(db, user, "create_product", {"name": "X", "photo_url": foreign})
            assert other["photo_url"] is None
        async with AsyncSessionLocal() as db:
            p = (await db.execute(select(Product).where(Product.advertiser_id == user_id))).scalar_one()
            assert p.price == Decimal("450.00") and p.photo_url == own and p.active
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_price_change_also_fixes_the_bot_instructions():
    user_id = await _seed_user(bot_instructions=INSTRUCTIONS)
    try:
        async with AsyncSessionLocal() as db:
            db.add(Product(advertiser_id=user_id, name="Corte", price=Decimal(150), active=True))
            await db.commit()
            user = await _user(db, user_id)
            summary, args, err = await _preview_confirm_tool(db, user, "update_product", {"product": "corte", "price": 180})
            assert err is None and "$150" in summary and "$180" in summary
            _, err = await _execute_confirm_tool(db, user, "update_product", args)
            assert err is None
        async with AsyncSessionLocal() as db:
            user = await _user(db, user_id)
            assert "- Corte — $180" in user.bot_instructions and "- Barba — $100" in user.bot_instructions
            p = (await db.execute(select(Product).where(Product.advertiser_id == user_id))).scalar_one()
            assert p.price == Decimal("180.00")
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_ambiguous_product_name_is_not_changed():
    user_id = await _seed_user()
    try:
        async with AsyncSessionLocal() as db:
            db.add(Product(advertiser_id=user_id, name="Corte niño", price=Decimal(100), active=True))
            db.add(Product(advertiser_id=user_id, name="Corte adulto", price=Decimal(150), active=True))
            await db.commit()
            user = await _user(db, user_id)
            summary, args, err = await _preview_confirm_tool(db, user, "update_product", {"product": "corte", "price": 1})
        assert summary is None and args is None and "nombre exacto" in err
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_hours_change_only_touches_the_days_said():
    user_id = await _seed_user(business_hours=WEEK, bot_instructions=INSTRUCTIONS)
    try:
        async with AsyncSessionLocal() as db:
            user = await _user(db, user_id)
            summary, args, err = await _preview_confirm_tool(
                db, user, "update_business_hours", {"changes": {"sat": ["09:00", "14:00"], "sun": None}},
            )
            assert err is None and "Sábado 09:00 a 14:00" in summary
            assert user.business_hours == WEEK  # todavía nada
            _, err = await _execute_confirm_tool(db, user, "update_business_hours", args)
            assert err is None
            _, _, bad = await _preview_confirm_tool(db, user, "update_business_hours", {"changes": {"mon": ["20:00", "10:00"]}})
            assert "no es válido" in bad
        async with AsyncSessionLocal() as db:
            user = await _user(db, user_id)
            assert user.business_hours["sat"] == ["09:00", "14:00"] and user.business_hours["mon"] == ["10:00", "20:00"]
            assert "Horario: Lunes 10:00–20:00; Martes" in user.bot_instructions
            assert "Sábado 09:00–14:00" in user.bot_instructions
    finally:
        await _cleanup(user_id)


def test_tools_registered_and_prompt_knows_today():
    names = {t["name"] for t in TOOLS}
    assert {"list_appointments", "list_orders", "list_products", "create_product", "update_product",
            "update_business_hours"} <= names
    prompt = _build_system_prompt(User(id=uuid.uuid4(), email="a@b.c", password_hash="x"))
    assert f"fecha {datetime.now(TZ):%Y-%m-%d}" in prompt


@pytest.mark.asyncio
async def test_loyalty_reward_is_asked_then_saved_only_after_confirmation():
    user_id = await _seed_user()
    try:
        async with AsyncSessionLocal() as db:
            user = await _user(db, user_id)
            # Tarjeta encendida por defecto pero sin premio: el Copiloto lo pide.
            assert "set_loyalty_reward" in _build_system_prompt(user)
            _, _, err = await _preview_confirm_tool(db, user, "set_loyalty_reward", {"reward": "  "})
            assert "premio" in err
            _, _, err = await _preview_confirm_tool(db, user, "set_loyalty_reward", {"reward": "Un corte", "stamps_required": 50})
            assert "3 a 20" in err
            summary, args, err = await _preview_confirm_tool(db, user, "set_loyalty_reward", {"reward": "Un corte gratis"})
            assert err is None and "8 sellos" in summary and "Un corte gratis" in summary
            assert user.loyalty_config is None  # todavía nada
            _, err = await _execute_confirm_tool(db, user, "set_loyalty_reward", args)
            assert err is None
        async with AsyncSessionLocal() as db:
            user = await _user(db, user_id)
            assert user.loyalty_config == {"enabled": True, "stamps_required": 8, "reward": "Un corte gratis"}
            assert "set_loyalty_reward" not in _build_system_prompt(user)
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_bot_status_lists_what_is_missing_and_clears_when_ready():
    from app.models.knowledge_base import KnowledgeBase

    user_id = await _seed_user(slug=f"bot-{uuid.uuid4().hex[:8]}")
    try:
        async with AsyncSessionLocal() as db:
            user = await _user(db, user_id)
            out = await _execute_immediate_tool(db, user, "get_bot_status", {})
            assert out["has_instructions"] is False and out["products"] == 0 and out["hours"] is None
            assert out["page_url"].endswith(f"/sitio/{user.slug}")
            assert any("instrucciones" in m for m in out["missing"])
            assert any("WhatsApp" in m for m in out["missing"])
            assert not any("página" in m for m in out["missing"])

            user.bot_instructions = INSTRUCTIONS
            user.business_hours = WEEK
            user.meta_connection_status = "connected"
            db.add_all([
                Product(advertiser_id=user_id, name="Corte", price=Decimal(150), active=True),
                Product(advertiser_id=user_id, name="Tinte", price=None, active=True),
                Product(advertiser_id=user_id, name="Oculto", price=None, active=False),
                KnowledgeBase(advertiser_id=user_id, filename="menu.pdf", file_type="pdf", processing_status="done"),
                KnowledgeBase(advertiser_id=user_id, filename="roto.pdf", file_type="pdf", processing_status="error"),
            ])
            await db.commit()
            out = await _execute_immediate_tool(db, user, "get_bot_status", {})
            assert out["products"] == 2 and out["products_without_price"] == 1 and out["documents"] == 1
            assert out["whatsapp_connected"] is True and "Lunes" in out["hours"]
            assert out["missing"] == ["precio en 1 producto(s)"]
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_test_bot_asks_the_real_pipeline_without_counting_a_conversation():
    from unittest.mock import AsyncMock, patch

    user_id = await _seed_user(business_name="Barbería Pepe", bot_name="Pepito")
    try:
        async with AsyncSessionLocal() as db:
            user = await _user(db, user_id)
            rag = AsyncMock(return_value="El corte cuesta $150 😊")
            with patch("app.services.rag_service.answer_with_rag", rag):
                out = await _execute_immediate_tool(db, user, "test_bot", {"question": "  ¿Cuánto   el corte? "})
                empty = await _execute_immediate_tool(db, user, "test_bot", {"question": "  "})
            assert out == {"question": "¿Cuánto el corte?", "answer": "El corte cuesta $150 😊"}
            kwargs = rag.await_args.kwargs
            assert kwargs["advertiser_id"] == str(user_id) and kwargs["bot_name"] == "Pepito"
            assert "conversation_key" not in kwargs
            assert "error" in empty and rag.await_count == 1
    finally:
        await _cleanup(user_id)


def test_bot_tools_are_registered_and_need_no_confirmation():
    names = {t["name"] for t in TOOLS}
    assert {"get_bot_status", "test_bot"} <= names
    assert not {"get_bot_status", "test_bot"} & CONFIRM_TOOLS
    assert biz.summarize("get_bot_status", {"missing": ["a", "b"]}) == "Revisé tu bot: le falta 2 cosa(s)."


@pytest.mark.asyncio
async def test_open_page_builder_opens_only_when_there_is_no_page():
    assert "open_page_builder" in {t["name"] for t in TOOLS}
    assert "open_page_builder" not in CONFIRM_TOOLS
    mk = lambda **kw: User(id=uuid.uuid4(), email="a@b.c", password_hash="x", **kw)  # noqa: E731
    out = await _execute_immediate_tool(None, mk(role="advertiser", slug=None), "open_page_builder", {})
    assert out == {"has_page": False}
    out = await _execute_immediate_tool(None, mk(role="advertiser", slug="pepe"), "open_page_builder", {})
    assert out["has_page"] is True and out["page_url"].endswith("/sitio/pepe")
    out = await _execute_immediate_tool(None, mk(role="admin", slug=None), "open_page_builder", {})
    assert "error" in out
    assert biz.summarize("open_page_builder", {"has_page": False}) == "Abrí el armador de tu página."
