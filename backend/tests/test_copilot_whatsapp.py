"""Copiloto por WhatsApp: mismo Copiloto del panel, transporte distinto —
historial en Redis y confirmación con botones "Sí, hazlo" / "Cancelar"."""
import json
import uuid
from unittest.mock import AsyncMock, patch

from app.models.user import User
from app.services import copilot_whatsapp_service as cw


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self.store[k] = v


def _owner() -> User:
    return User(id=uuid.uuid4(), business_name="Taquería Don Pepe")


def test_parse_decision():
    assert cw.parse_decision("✅ Sí, hazlo") is True
    assert cw.parse_decision("si") is True
    assert cw.parse_decision("Dale!") is True
    assert cw.parse_decision("❌ Cancelar") is False
    assert cw.parse_decision("mejor no") is False
    assert cw.parse_decision("sí, pero a los de Oaxaca") is None


async def _run(owner, text, redis, chat=None, confirm=None):
    with (
        patch.object(cw, "get_redis_optional", AsyncMock(return_value=redis)),
        patch.object(cw, "handle_chat", chat or AsyncMock(return_value={"reply": "Tienes 3 citas.", "pending_confirmation": None})) as hc,
        patch.object(cw, "handle_confirm", confirm or AsyncMock(return_value={"reply": "Hecho ✅"})) as hf,
        patch.object(cw, "send_platform_text", AsyncMock(return_value=("w", None))) as st,
        patch.object(cw, "send_platform_buttons", AsyncMock(return_value=("w", None))) as sb,
    ):
        await cw.handle_owner_command(None, owner=owner, from_number="+5215512345678", text=text)
    return hc, hf, st, sb


async def test_question_uses_whatsapp_channel_and_keeps_history():
    owner, redis = _owner(), FakeRedis()
    hc, _, st, _ = await _run(owner, "¿cuántas citas tengo?", redis)
    assert hc.call_args.kwargs["channel"] == "whatsapp"
    assert st.call_args.args[1] == "Tienes 3 citas."
    await _run(owner, "¿y pasado mañana?", redis)
    history = json.loads(redis.store[f"copilot_wa:{owner.id}"])["history"]
    assert [h["content"] for h in history][:2] == ["¿cuántas citas tengo?", "Tienes 3 citas."]


async def test_sensitive_action_asks_with_buttons_then_confirms():
    owner, redis = _owner(), FakeRedis()
    chat = AsyncMock(return_value={
        "reply": "Voy a lanzar *Promo 2x1* a 120 contactos.",
        "pending_confirmation": {"confirmation_id": "tok-1", "tool": "launch_campaign", "summary": "x", "args": {}},
    })
    _, _, _, sb = await _run(owner, "lanza la promo 2x1", redis, chat=chat)
    assert sb.call_args.args[2] == cw.CONFIRM_BUTTONS

    _, hf, st, _ = await _run(owner, "✅ Sí, hazlo", redis)
    assert hf.call_args.args[2:4] == ("tok-1", True)
    assert st.call_args.args[1] == "Hecho ✅"
    assert json.loads(redis.store[f"copilot_wa:{owner.id}"])["pending"] is None


async def test_other_message_discards_pending_action():
    # Nunca se ejecuta algo que el dueño no confirmó explícitamente.
    owner, redis = _owner(), FakeRedis()
    redis.store[f"copilot_wa:{owner.id}"] = json.dumps({"history": [], "pending": "tok-1"})
    hc, hf, _, _ = await _run(owner, "mejor dime cuántos contactos tengo", redis)
    hf.assert_not_called()
    hc.assert_awaited_once()
    assert json.loads(redis.store[f"copilot_wa:{owner.id}"])["pending"] is None


async def test_without_redis_never_leaves_an_unconfirmable_action():
    chat = AsyncMock(return_value={"reply": "Voy a lanzarla.", "pending_confirmation": {"confirmation_id": "t"}})
    _, _, st, sb = await _run(_owner(), "lanza la promo", None, chat=chat)
    sb.assert_not_called()
    assert "panel" in st.call_args.args[1]
