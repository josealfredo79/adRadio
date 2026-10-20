"""Agente del cliente por la cadena de modelos: gratis primero, Claude Haiku
al final (spec docs/specs/2026-10-19-agente-cliente-cadena-gratis.md).
Modelos simulados; base y Redis reales para ver que nada se agenda sin el "sí"."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx
import pytest
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.appointment import Appointment
from app.services import customer_agent as agent
from app.services import llm_client

# Las llaves y register_bot_conversation simulados de test_customer_agent.
from tests.test_customer_agent import (
    Redis,
    _cleanup,
    _keys,  # noqa: F401
    _next_open_day,
    _say,
    _seed,
    resp,
    text,
    tool,
)


def _call(name, args, call_id="call_1"):
    arguments = args if isinstance(args, str) else json.dumps(args)
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def _reply(content=None, calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=calls))])


def _free(*replies):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=list(replies)))))


def _chain(**clients):
    return lambda *a, **k: [(name, lambda: True, (lambda c=c: c), lambda: ["modelo"]) for name, c in clients.items()]


def _claude(*responses):
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=list(responses))
    return patch("app.services.customer_agent._get_client", return_value=client), client


def _no_balance():
    return anthropic.BadRequestError(
        "Your credit balance is too low",
        response=httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")),
        body=None,
    )


def _tool_results(free_client) -> list[dict]:
    messages = free_client.chat.completions.create.await_args_list[-1].kwargs["messages"]
    return [json.loads(m["content"]) for m in messages if m["role"] == "tool"]


@pytest.mark.asyncio
async def test_caso1_free_model_answers_without_claude():
    user_id, ana, *_ = await _seed()
    gemini = _free(_reply(calls=[_call("mis_sellos", {})]), _reply("Llevas 0 de 5 sellos."))
    claude, client = _claude()
    try:
        with patch.object(llm_client, "_free_providers", _chain(Gemini=gemini)):
            out = await _say(user_id, ana, "¿cuántos sellos llevo?", Redis(), claude)
        assert out.text == "Llevas 0 de 5 sellos." and client.messages.create.await_count == 0
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso2_free_model_proposes_and_nothing_is_booked_until_yes():
    user_id, ana, *_ = await _seed()
    r = Redis()
    when = _next_open_day()
    gemini = _free(
        _reply(calls=[_call("horarios_libres", {"fecha": when.date().isoformat()})]),
        _reply(calls=[_call("proponer_cita", {"servicio": "Mesa para 4", "fecha_hora": when.strftime("%Y-%m-%dT%H:%M")},
                            "call_2")]),
        _reply("Tengo a las 5 pm para 4. ¿Lo confirmo?"),
    )
    try:
        with patch.object(llm_client, "_free_providers", _chain(Gemini=gemini)):
            out = await _say(user_id, ana, "¿tienes lugar mañana en la tarde para 4?", r)
        assert out.confirm is True and "17:00" in _tool_results(gemini)[0]["horarios"]
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(Appointment).where(Appointment.contact_id == ana))).first() is None

        out = await _say(user_id, ana, "sí", r)
        assert out.text.startswith("✅ ¡Listo! Tu cita de Mesa para 4")
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(Appointment).where(Appointment.contact_id == ana))).scalar_one()
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso3_forced_tool_is_forced_on_the_free_model_too():
    user_id, ana, *_ = await _seed()
    gemini = _free(_reply(calls=[_call("mis_pedidos", {})]), _reply("No tienes pedidos."))
    try:
        with patch.object(llm_client, "_free_providers", _chain(Gemini=gemini)):
            await _say(user_id, ana, "cancela mi pedido", Redis())
        calls = gemini.chat.completions.create.await_args_list
        assert calls[0].kwargs["tool_choice"] == {"type": "function", "function": {"name": "mis_pedidos"}}
        assert "tool_choice" not in calls[1].kwargs
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso4_provider_fails_mid_turn_next_one_continues_without_repeating_tools():
    user_id, ana, *_ = await _seed()
    when = _next_open_day()
    gemini = _free(_reply(calls=[_call("horarios_libres", {"fecha": when.date().isoformat()})]), RuntimeError("cuota"))
    groq = _free(_reply("A las 5 pm hay lugar. ¿Quieres que te la aparte?"))
    horarios = AsyncMock(return_value={"horarios": ["17:00"]})
    try:
        with patch.object(llm_client, "_free_providers", _chain(Gemini=gemini, Groq=groq)), \
                patch.dict(agent._HANDLERS, {"horarios_libres": horarios}):
            await _say(user_id, ana, "¿tienes lugar mañana en la tarde?", Redis())
        assert horarios.await_count == 1
        # Groq recibió el historial con el resultado que ya se había sacado.
        assert _tool_results(groq) == [{"horarios": ["17:00"]}]
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso5_all_free_fail_falls_back_to_haiku():
    user_id, ana, *_ = await _seed()
    gemini = _free(RuntimeError("caído"))
    claude, client = _claude(resp(tool("mis_sellos")), resp(text("Llevas 0 de 5."), stop="end_turn"))
    try:
        with patch.object(llm_client, "_free_providers", _chain(Gemini=gemini)):
            out = await _say(user_id, ana, "¿cuántos sellos llevo?", Redis(), claude)
        assert out.text == "Llevas 0 de 5."
        assert client.messages.create.await_args_list[0].kwargs["model"] == settings.CUSTOMER_AGENT_MODEL
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso6_everything_fails_goes_to_the_fixed_flows():
    user_id, ana, *_ = await _seed()
    claude, _ = _claude(_no_balance())
    try:
        with patch.object(llm_client, "_free_providers", _chain(Gemini=_free(RuntimeError("caído")))):
            assert await _say(user_id, ana, "quiero agendar una cita", Redis(), claude) is None
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso7_claim_guard_works_with_free_models():
    """Dice "¡Listo, agendada!" sin proponer nada: se le corrige y no queda nada agendado."""
    user_id, ana, *_ = await _seed()
    gemini = _free(_reply("¡Listo! Tu cita quedó agendada."), _reply("¿A qué hora te gustaría?"))
    try:
        with patch.object(llm_client, "_free_providers", _chain(Gemini=gemini)):
            out = await _say(user_id, ana, "agéndame mañana", Redis())
        assert out.text == "¿A qué hora te gustaría?" and gemini.chat.completions.create.await_count == 2
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(Appointment).where(Appointment.contact_id == ana))).first() is None
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_bad_tool_arguments_go_back_as_error():
    user_id, ana, *_ = await _seed()
    gemini = _free(_reply(calls=[_call("mis_sellos", "{roto")]), _reply("Perdón, ¿me repites?"))
    try:
        with patch.object(llm_client, "_free_providers", _chain(Gemini=gemini)):
            out = await _say(user_id, ana, "¿cuántos sellos llevo?", Redis())
        assert out.text == "Perdón, ¿me repites?" and "error" in _tool_results(gemini)[0]
    finally:
        await _cleanup(user_id)


def test_agent_is_available_with_only_free_models(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    with patch.object(llm_client, "_free_providers", _chain(Gemini=_free())):
        assert agent.agent_available(SimpleNamespace(customer_agent_enabled=True), object()) is True
    with patch.object(llm_client, "_free_providers", lambda *a, **k: []):
        assert agent.agent_available(SimpleNamespace(customer_agent_enabled=True), object()) is False
