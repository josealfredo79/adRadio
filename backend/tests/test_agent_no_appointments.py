"""El agente del cliente ya no le dice "SÍ agenda" a un negocio que no da citas.

Prueba real CityCell 2026-11-10: tienda de celulares, el bot ofreció
"¿quieres agendar una reparación?". Los restaurantes siguen apartando mesa.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.database import AsyncSessionLocal
from app.models.user import User
from app.services import customer_agent as agent
from app.services import rag_service
from app.services.chat_quick_asks import (
    ASK_APPOINTMENT,
    chat_quick_asks_for,
    takes_appointments,
)


def _user(category: str) -> User:
    return User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Negocio",
                business_category=category)


def test_shop_prompt_says_no_appointments():
    prompt = agent._stable_system(_user("Tienda de celulares"), takes_appointments=False)
    assert "Este negocio SÍ agenda" not in prompt
    assert "NO da citas ni agenda servicios (ni reparaciones" in prompt
    assert "Servicios que se agendan" not in prompt


def test_booking_prompt_unchanged():
    prompt = agent._stable_system(_user("Estética"), takes_appointments=True)
    assert "Este negocio SÍ agenda" in prompt
    assert "NO da citas" not in prompt


@pytest.mark.asyncio
async def test_shop_tools_refuse_to_book():
    ctx = SimpleNamespace(takes_appointments=False)
    for tool in (agent._tool_horarios_libres, agent._tool_proponer_cita):
        out = await tool(ctx, {"fecha": "2030-01-01", "servicio": "Reparación", "fecha_hora": "2030-01-01T10:00"})
        assert out == {"error": agent.NO_APPOINTMENTS_ERROR}


@pytest.mark.asyncio
async def test_restaurant_still_reserves_but_gets_no_appointment_button():
    async with AsyncSessionLocal() as db:
        fonda = _user("restaurante")
        shop = _user("Tienda de celulares")
        salon = _user("Estética")
        db.add_all([fonda, shop, salon])
        await db.commit()
        try:
            assert await takes_appointments(db, fonda) is True
            assert await takes_appointments(db, shop) is False
            assert ASK_APPOINTMENT not in await chat_quick_asks_for(db, fonda)
            assert ASK_APPOINTMENT not in await chat_quick_asks_for(db, shop)
            assert ASK_APPOINTMENT in await chat_quick_asks_for(db, salon)
        finally:
            for u in (fonda, shop, salon):
                await db.delete(u)
            await db.commit()


def test_whatsapp_rule_names_repairs():
    assert "reparación" in rag_service.NO_APPOINTMENTS_FACT
