"""Copiloto con la cadena de modelos, gratis primero y Claude al final
(spec docs/specs/2026-10-18-copiloto-cadena-gratis.md). Los proveedores se
simulan; la base y Redis son reales (las ventas se guardan de verdad)."""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.loyalty_stamp import LoyaltyStamp
from app.models.sale import Sale
from app.models.user import User
from app.services import copilot_service, llm_client


def _call(name: str, args, call_id: str = "call_1"):
    arguments = args if isinstance(args, str) else json.dumps(args)
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def _openai_reply(text: str | None = None, calls: list | None = None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=calls))])


def _free_client(*replies):
    """Cliente compatible con OpenAI: cada respuesta es un reply o una excepción."""
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=list(replies)))))


def _chain(**clients):
    return lambda *a, **k: [(name, lambda: True, (lambda c=c: c), lambda: ["modelo"]) for name, c in clients.items()]


@pytest.fixture
def anthropic_mock():
    create = AsyncMock(return_value=SimpleNamespace(content=[SimpleNamespace(type="text", text="Hola desde Claude")]))
    with patch.object(llm_client, "_get_anthropic_client", return_value=SimpleNamespace(messages=SimpleNamespace(create=create))):
        yield create


def _user(role: str = "admin") -> User:
    return User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", business_name="CityCell",
                current_plan="enterprise", role=role)


@pytest.fixture(autouse=True)
def _no_push():
    with patch("app.services.loyalty_service.notify_stamp", new=AsyncMock()):
        yield


@pytest.fixture
async def owner():
    await engine.dispose()
    tail = f"{uuid.uuid4().int % 10**6:06d}"
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="CityCell", role="admin")
        db.add(user)
        await db.flush()
        db.add(Contact(advertiser_id=user.id, name="Juan Pérez", phone=f"+52953{tail}1234"))
        await db.commit()
        uid = user.id
    yield uid
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Sale).where(Sale.advertiser_id == uid))
        await db.execute(delete(LoyaltyStamp).where(LoyaltyStamp.advertiser_id == uid))
        await db.execute(delete(Contact).where(Contact.advertiser_id == uid))
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()
    await engine.dispose()


async def _chat(owner_id, message: str) -> dict:
    async with AsyncSessionLocal() as db:
        user = await db.get(User, owner_id)
        return await copilot_service.handle_chat(db, user, message, [])


async def _sales(owner_id) -> list[Sale]:
    async with AsyncSessionLocal() as db:
        return list((await db.execute(select(Sale).where(Sale.advertiser_id == owner_id))).scalars().all())


@pytest.mark.asyncio
async def test_free_model_answers_without_claude(anthropic_mock):
    groq = _free_client(_openai_reply("¡Hola! ¿En qué te ayudo?"))
    with patch.object(llm_client, "_free_providers", _chain(Groq=groq)):
        out = await copilot_service.handle_chat(None, _user(), "hola", [])
    assert out["reply"] == "¡Hola! ¿En qué te ayudo?"
    anthropic_mock.assert_not_called()
    sent = groq.chat.completions.create.await_args.kwargs
    assert sent["messages"][0]["role"] == "system"
    assert {t["function"]["name"] for t in sent["tools"]} == {t["name"] for t in copilot_service._tools_for("panel")}


@pytest.mark.asyncio
async def test_free_model_runs_tools_and_sees_results(owner, anthropic_mock):
    groq = _free_client(_openai_reply(calls=[_call("record_sale", {"amount": 85, "customer": "juan"})]),
                        _openai_reply("Listo, registré $85 a Juan Pérez."))
    with patch.object(llm_client, "_free_providers", _chain(Groq=groq)):
        out = await _chat(owner, "cobré 85 a Juan")
    assert out["reply"] == "Listo, registré $85 a Juan Pérez."
    assert [a["tool"] for a in out["actions"]] == ["record_sale"]
    sales = await _sales(owner)
    assert len(sales) == 1 and float(sales[0].amount) == 85
    second = groq.chat.completions.create.await_args_list[1].kwargs["messages"]
    assert second[-2]["tool_calls"][0]["function"]["name"] == "record_sale"
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "call_1"
    assert "85" in second[-1]["content"]
    anthropic_mock.assert_not_called()


@pytest.mark.asyncio
async def test_provider_fails_mid_turn_next_one_continues(owner, anthropic_mock):
    gemini = _free_client(_openai_reply(calls=[_call("record_sale", {"amount": 85, "customer": "juan"})]),
                          RuntimeError("429 cuota agotada"))
    groq = _free_client(_openai_reply("Registré $85 a Juan."))
    with patch.object(llm_client, "_free_providers", _chain(Gemini=gemini, Groq=groq)):
        out = await _chat(owner, "cobré 85 a Juan")
    assert out["reply"] == "Registré $85 a Juan."
    assert len(await _sales(owner)) == 1  # la venta no se repite al cambiar de modelo
    handed = groq.chat.completions.create.await_args.kwargs["messages"]
    assert handed[-1]["role"] == "tool" and "85" in handed[-1]["content"]
    anthropic_mock.assert_not_called()


@pytest.mark.asyncio
async def test_all_free_fail_falls_back_to_claude(anthropic_mock):
    groq = _free_client(RuntimeError("caído"))
    gemini = _free_client(_openai_reply(""))  # vacío también cuenta como falla
    with patch.object(llm_client, "_free_providers", _chain(Groq=groq, Gemini=gemini)):
        out = await copilot_service.handle_chat(None, _user(), "hola", [])
    assert out["reply"] == "Hola desde Claude"
    tools = anthropic_mock.await_args.kwargs["tools"]
    assert tools[-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in copilot_service.TOOLS[-1]  # no se ensucia la lista original


@pytest.mark.asyncio
async def test_everything_fails_friendly_reply(anthropic_mock):
    anthropic_mock.side_effect = RuntimeError("Your credit balance is too low")
    with patch.object(llm_client, "_free_providers", _chain(Groq=_free_client(RuntimeError("caído")))):
        out = await copilot_service.handle_chat(None, _user(), "hola", [])
    assert out["reply"].startswith("Tuve un problema")
    assert out["pending_confirmation"] is None


@pytest.mark.asyncio
async def test_free_model_confirm_tool_returns_card(anthropic_mock):
    groq = _free_client(_openai_reply(calls=[_call("create_product", {"name": "Funda", "price": 120})]))
    with patch.object(llm_client, "_free_providers", _chain(Groq=groq)):
        out = await copilot_service.handle_chat(None, _user(), "agrega funda a 120", [])
    pending = out["pending_confirmation"]
    assert pending["tool"] == "create_product"
    assert pending["args"]["name"] == "Funda" and pending["confirmation_id"]
    assert out["reply"]  # pregunta antes de hacerlo


@pytest.mark.asyncio
async def test_confirmed_result_uses_chain(anthropic_mock):
    groq = _free_client(_openai_reply("Listo, ya está la Funda en tu catálogo."))
    with patch.object(llm_client, "_free_providers", _chain(Groq=groq)):
        text = await copilot_service._phrase_confirmed_result(_user(), "create_product", {"name": "Funda"})
    assert text == "Listo, ya está la Funda en tu catálogo."
    anthropic_mock.assert_not_called()


@pytest.mark.asyncio
async def test_bad_tool_arguments_returned_as_error(anthropic_mock):
    groq = _free_client(_openai_reply(calls=[_call("record_sale", '{"amount": 85,')]),
                        _openai_reply("Perdón, ¿de cuánto fue el cobro?"))
    with patch.object(llm_client, "_free_providers", _chain(Groq=groq)):
        out = await copilot_service.handle_chat(None, _user(), "cobré 85", [])
    assert out["reply"] == "Perdón, ¿de cuánto fue el cobro?"
    assert out["actions"] == []
    result = groq.chat.completions.create.await_args_list[1].kwargs["messages"][-1]
    assert result["role"] == "tool" and "inválidos" in result["content"]


@pytest.mark.asyncio
async def test_gemini_signature_goes_back_and_never_reaches_claude(anthropic_mock):
    """Gemini 3 rechaza la segunda vuelta si no le regresan su firma; Anthropic
    rechaza campos que no conoce."""
    call = _call("get_sales_today", {})
    call.model_extra = {"extra_content": {"google": {"thought_signature": "firma-123"}}}
    gemini = _free_client(_openai_reply(calls=[call]), RuntimeError("cuota"))
    with patch.object(llm_client, "_free_providers", _chain(Gemini=gemini)), \
         patch.object(copilot_service, "_execute_immediate_tool", AsyncMock(return_value={"total": 170})):
        out = await copilot_service.handle_chat(None, _user(), "¿cuánto llevo hoy?", [])
    assert out["reply"] == "Hola desde Claude"
    second = gemini.chat.completions.create.await_args_list[1].kwargs["messages"]
    assert second[-2]["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == "firma-123"
    for m in anthropic_mock.await_args.kwargs["messages"]:
        if isinstance(m["content"], list):
            assert all("openai_extra" not in b for b in m["content"])


@pytest.mark.asyncio
async def test_cloudflare_is_skipped_for_tools(anthropic_mock):
    cloudflare = _free_client(_openai_reply("no debería contestar"))
    gemini = _free_client(_openai_reply("¡Hola!"))
    with patch.object(llm_client, "_free_providers", _chain(Cloudflare=cloudflare, Gemini=gemini)):
        out = await copilot_service.handle_chat(None, _user(), "hola", [])
    assert out["reply"] == "¡Hola!"
    cloudflare.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_gemini_goes_first_for_tools(anthropic_mock):
    """Groq comparte su tope por minuto con el bot de los clientes: en el
    Copiloto va después de Gemini."""
    groq = _free_client(_openai_reply("soy Groq"))
    gemini = _free_client(_openai_reply("soy Gemini"))
    with patch.object(llm_client, "_free_providers", _chain(Groq=groq, Gemini=gemini)):
        out = await copilot_service.handle_chat(None, _user(), "hola", [])
    assert out["reply"] == "soy Gemini"
    groq.chat.completions.create.assert_not_called()


# Caso real (19-oct): "Llevas 1 venta por un total de 85.0 pesos" aunque la herramienta ya manda 85.
@pytest.mark.parametrize("raw,clean", [
    ("Cobré 30.0 pesos. Llevas $165.0 hoy.", "Cobré 30 pesos. Llevas $165 hoy."),
    ("Total de 1,250.0 pesos", "Total de 1,250 pesos"),
    ("Llevas $165.00 y $85.50", "Llevas $165.00 y $85.50"),
    ("La versión 2.0 del menú", "La versión 2.0 del menú"),
])
def test_tidy_money_drops_point_zero_only_on_amounts(raw, clean):
    assert copilot_service._tidy_money(raw) == clean
