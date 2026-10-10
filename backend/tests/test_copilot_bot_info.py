"""Copiloto: update_bot_info (copilot_business_tools.py) — el dueño cambia lo que su
bot sabe (dirección, pagos, preguntas frecuentes, políticas) pidiéndolo en el chat.

Lo crítico: pasa por la confirmación, solo toca los temas que pidió, y no borra ni
pisa lo demás (precios, horario, texto propio, otras preguntas frecuentes)."""
import uuid

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal, engine
from app.models.user import User
from app.services import copilot_business_tools as biz
from app.services.copilot_service import (
    CONFIRM_TOOLS,
    TOOLS,
    _execute_confirm_tool,
    _execute_immediate_tool,
    _preview_confirm_tool,
)

INSTRUCTIONS = (
    "Ubicación: Calle Hidalgo 12, Tlaxiaco\n\n"
    "Horario: Lunes 10:00–20:00\n\n"
    "Servicios y precios:\n- Corte — $150\n\n"
    "Formas de pago: efectivo\n\n"
    "Preguntas frecuentes:\nP: ¿Atienden niños?\nR: Sí, desde los 3 años\nP: ¿Hacen envíos?\nR: No por ahorita\n\n"
    "Nunca des descuentos por WhatsApp."
)


async def _seed(**kw) -> uuid.UUID:
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", city="Tlaxiaco",
                    bot_instructions=INSTRUCTIONS, **kw)
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


async def _run(user_id, args) -> tuple[str | None, str | None, str | None]:
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
        summary, resolved, err = await _preview_confirm_tool(db, user, "update_bot_info", args)
        if err:
            return summary, None, err
        _, err = await _execute_confirm_tool(db, user, "update_bot_info", resolved)
        await db.refresh(user)
        return summary, user.bot_instructions, err


def test_is_a_confirmed_tool():
    assert "update_bot_info" in CONFIRM_TOOLS and "update_bot_info" in {t["name"] for t in TOOLS}


@pytest.mark.asyncio
async def test_payment_change_keeps_everything_else():
    user_id = await _seed()
    try:
        summary, text, err = await _run(user_id, {"payment_methods": ["Efectivo", "Tarjeta"]})
        assert err is None and "Efectivo, Tarjeta" in summary
        assert "Formas de pago: Efectivo, Tarjeta" in text and "Formas de pago: efectivo" not in text
        for kept in ("Calle Hidalgo 12", "Horario: Lunes", "- Corte — $150", "¿Atienden niños?", "Nunca des descuentos"):
            assert kept in text
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_add_and_remove_faqs_and_add_policy():
    user_id = await _seed()
    try:
        _, text, err = await _run(user_id, {
            "add_faqs": [{"q": "¿Aceptan tarjeta?", "a": "Sí, con terminal"}],
            "remove_faqs": ["envíos"],
            "add_policies": ["Garantía de 30 días"],
        })
        assert err is None
        assert "¿Aceptan tarjeta?" in text and "¿Atienden niños?" in text and "¿Hacen envíos?" not in text
        assert "Garantía de 30 días" in text
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_removing_the_last_faq_removes_the_topic():
    user_id = await _seed()
    try:
        _, text, _ = await _run(user_id, {"remove_faqs": ["niños", "envíos"]})
        assert "Preguntas frecuentes" not in text and "Nunca des descuentos" in text
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_address_change_updates_city_column_too():
    user_id = await _seed()
    try:
        _, text, err = await _run(user_id, {"address": "Calle Juárez 3", "city": "Oaxaca"})
        assert err is None and "Ubicación: Calle Juárez 3, Oaxaca" in text and "Hidalgo" not in text
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(User.city).where(User.id == user_id))).scalar_one() == "Oaxaca"
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_preview_saves_nothing_and_no_op_is_refused():
    user_id = await _seed()
    try:
        async with AsyncSessionLocal() as db:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
            _, resolved, err = await _preview_confirm_tool(db, user, "update_bot_info", {"payment_methods": ["Tarjeta"]})
            assert err is None and resolved
            await db.refresh(user)
            assert user.bot_instructions == INSTRUCTIONS
            _, _, same = await _preview_confirm_tool(db, user, "update_bot_info", {"payment_methods": ["efectivo"]})
            _, _, empty = await _preview_confirm_tool(db, user, "update_bot_info", {})
        assert same and "ya sabe" in same and empty
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("said,hex_", [("verde", "#2f9e44"), ("Café", "#8a5a2b"), ("#ABC", "#aabbcc"), ("#E03131", "#e03131")])
async def test_page_color_change_by_name_or_hex(said, hex_):
    user_id = await _seed(widget_color="#000000")
    try:
        assert "update_page_style" in CONFIRM_TOOLS
        async with AsyncSessionLocal() as db:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
            summary, resolved, err = await _preview_confirm_tool(db, user, "update_page_style", {"color": said})
            assert err is None and said in summary
            await db.refresh(user)
            assert user.widget_color == "#000000"  # la vista previa no guarda nada
            _, err = await _execute_confirm_tool(db, user, "update_page_style", resolved)
            assert err is None
            await db.refresh(user)
            assert user.widget_color == hex_
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_page_style_rejects_unknown_values_and_no_ops():
    user_id = await _seed(widget_color="#2f9e44", site_theme="claro")
    try:
        async with AsyncSessionLocal() as db:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
            _, _, bad_color = await _preview_confirm_tool(db, user, "update_page_style", {"color": "brillante"})
            _, _, bad_theme = await _preview_confirm_tool(db, user, "update_page_style", {"theme": "neon"})
            _, _, same = await _preview_confirm_tool(db, user, "update_page_style", {"color": "verde", "theme": "claro"})
            _, resolved, err = await _preview_confirm_tool(db, user, "update_page_style", {"theme": "crema"})
            assert bad_color and "No reconozco" in bad_color and bad_theme and same and "ya está así" in same
            _, err = await _execute_confirm_tool(db, user, "update_page_style", resolved)
            await db.refresh(user)
            assert err is None and user.site_theme == "crema" and user.widget_color == "#2f9e44"
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_open_page_builder_edit_flag_only_with_a_page():
    from types import SimpleNamespace as mk

    page = await _execute_immediate_tool(None, mk(role="advertiser", slug="pepe"), "open_page_builder", {"edit": True})
    assert page["has_page"] is True and page["edit"] is True
    plain = await _execute_immediate_tool(None, mk(role="advertiser", slug="pepe"), "open_page_builder", {})
    assert "edit" not in plain
    assert biz.summarize("open_page_builder", page) == "Abrí el armador con lo que ya tiene tu página."
