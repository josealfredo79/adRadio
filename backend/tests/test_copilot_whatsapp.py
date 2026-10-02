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


# ─── Cero fricción: nota de voz → nota de voz; fotos de productos ───────────

async def _run_voice(owner, text, redis, *, voice=False, photo_url=None, audio_ok=True, chat=None):
    with (
        patch.object(cw, "get_redis_optional", AsyncMock(return_value=redis)),
        patch.object(cw, "handle_chat", chat or AsyncMock(return_value={"reply": "Tienes *3 citas* hoy.", "pending_confirmation": None})) as hc,
        patch.object(cw, "_voice_note_url", AsyncMock(return_value="https://x/copilot_voice/a.ogg" if audio_ok else None)) as vn,
        patch.object(cw, "send_platform_audio", AsyncMock(return_value=("w", None))) as sa,
        patch.object(cw, "send_platform_text", AsyncMock(return_value=("w", None))) as st,
        patch.object(cw, "send_platform_buttons", AsyncMock(return_value=("w", None))) as sb,
    ):
        await cw.handle_owner_command(None, owner=owner, from_number="+5215512345678", text=text, voice=voice, photo_url=photo_url)
    return hc, vn, sa, st, sb


async def test_voice_note_gets_a_voice_note_back_in_voice_mode():
    owner = _owner()
    hc, vn, sa, st, _ = await _run_voice(owner, "¿qué citas tengo hoy?", FakeRedis(), voice=True)
    assert hc.call_args.kwargs["channel"] == "voz"
    assert vn.call_args.args[1] == "Tienes *3 citas* hoy."
    assert sa.call_args.args == ("+5215512345678", "https://x/copilot_voice/a.ogg")
    st.assert_not_called()


async def test_voice_reply_falls_back_to_text_and_text_stays_text():
    _, _, sa, st, _ = await _run_voice(_owner(), "¿qué citas tengo?", FakeRedis(), voice=True, audio_ok=False)
    sa.assert_not_called()
    assert st.call_args.args[1] == "Tienes *3 citas* hoy."
    hc, vn, sa, st, _ = await _run_voice(_owner(), "¿qué citas tengo?", FakeRedis())
    assert hc.call_args.kwargs["channel"] == "whatsapp"
    vn.assert_not_called()
    sa.assert_not_called()


async def test_confirmations_stay_as_buttons_even_by_voice():
    chat = AsyncMock(return_value={"reply": "¿Agrego el tinte a 450?", "pending_confirmation": {"confirmation_id": "t"}})
    _, _, sa, _, sb = await _run_voice(_owner(), "agrega el tinte a 450", FakeRedis(), voice=True, chat=chat)
    sa.assert_not_called()
    assert sb.call_args.args[2] == cw.CONFIRM_BUTTONS


async def test_photo_alone_is_kept_and_used_by_the_next_instruction():
    owner, redis = _owner(), FakeRedis()
    url = f"https://x/api/v1/radio/audio/products/{owner.id}/a.jpg"
    hc, _, _, st, _ = await _run_voice(owner, "", redis, photo_url=url)
    hc.assert_not_called()
    assert st.call_args.args[1] == cw._PHOTO_PROMPT
    hc, *_ = await _run_voice(owner, "es un tinte, 450 pesos", redis, voice=True)
    assert hc.call_args.args[2] == f"es un tinte, 450 pesos\n[Foto adjunta: {url}]"
    # Se usa una sola vez.
    hc, *_ = await _run_voice(owner, "¿qué citas tengo?", redis)
    assert "[Foto adjunta" not in hc.call_args.args[2]


async def test_photo_with_caption_goes_straight_to_the_copilot():
    owner = _owner()
    url = f"https://x/api/v1/radio/audio/products/{owner.id}/b.jpg"
    hc, *_ = await _run_voice(owner, "tinte a 450", FakeRedis(), photo_url=url)
    assert hc.call_args.args[2] == f"tinte a 450\n[Foto adjunta: {url}]"


async def test_owner_photo_is_stored_where_the_copilot_accepts_it():
    owner = _owner()
    with patch.object(cw, "upload_bytes", AsyncMock(side_effect=lambda c, key, ct: f"https://x/api/v1/radio/audio/{key}")) as up:
        url = await cw.save_owner_photo(owner, b"jpg", "image/jpeg")
        assert f"products/{owner.id}/" in url and url.endswith(".jpg")
        assert await cw.save_owner_photo(owner, b"gif", "image/gif") is None
    assert up.await_count == 1


def test_speakable_strips_whatsapp_formatting():
    assert cw._speakable("*Hoy*:\n- Ana a las 5\n- Beto a las 6") == "Hoy: Ana a las 5 Beto a las 6"


async def test_webhook_passes_voice_and_photo_to_the_owner_flow():
    from app.api.v1.webhooks_pkg import meta_incoming as mi

    with (
        patch.object(mi, "download_media", AsyncMock(return_value=(b"bytes", "image/jpeg"))),
        patch.object(mi, "transcribe_audio_bytes", AsyncMock(return_value="¿qué pedidos tengo?")),
        patch.object(mi, "handle_owner_message", AsyncMock()) as hom,
    ):
        await mi._handle_platform_message(None, {"from": "5215512345678", "type": "audio", "audio": {"id": "m1"}})
        assert hom.call_args.kwargs["text"] == "¿qué pedidos tengo?" and hom.call_args.kwargs["voice"] is True
        await mi._handle_platform_message(None, {"from": "5215512345678", "type": "image", "image": {"id": "m2", "caption": "tinte a 450"}})
        assert hom.call_args.kwargs["photo"] == (b"bytes", "image/jpeg")
        assert hom.call_args.kwargs["text"] == "tinte a 450" and hom.call_args.kwargs["voice"] is False


async def _webhook(monkeypatch, *, bot_on_number: bool, owners: set[str]):
    """Mensajes al número central: uno de un dueño registrado y uno de alguien más."""
    from unittest.mock import MagicMock

    from starlette.requests import Request

    from app.api.v1.webhooks_pkg import meta_incoming as mi

    monkeypatch.setattr(mi.settings, "IARADIO_WA_PHONE_NUMBER_ID", "999")
    monkeypatch.setattr(mi.settings, "IARADIO_WA_TOKEN", "tok")
    payload = {"entry": [{"id": "waba", "changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "999"},
        "messages": [
            {"from": "5215511111111", "id": "w1", "type": "text", "text": {"body": "¿qué citas tengo?"}},
            {"from": "5215522222222", "id": "w2", "type": "text", "text": {"body": "¿cuánto cuesta IaRadio?"}},
        ],
    }}]}]}
    body = json.dumps(payload).encode()

    async def receive():
        return {"type": "http.request", "body": body}

    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("t", 1), "query_string": b""}, receive)
    result = MagicMock()
    result.first.return_value = ("bot-user-id",) if bot_on_number else None
    result.scalar_one_or_none.return_value = None  # el pipeline normal se detiene aquí
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    with (
        patch.object(mi, "_validate_signature", AsyncMock(return_value=True)),
        patch.object(mi, "is_registered_owner", AsyncMock(side_effect=lambda _db, n: n in owners)),
        patch.object(mi, "_handle_platform_message", AsyncMock()) as hpm,
    ):
        await mi.meta_incoming.__wrapped__(request, db=db)
    return hpm, db


async def test_central_number_owner_gets_copilot_and_others_get_the_bot(monkeypatch):
    hpm, db = await _webhook(monkeypatch, bot_on_number=True, owners={"+5215511111111"})
    assert [c.args[1]["id"] for c in hpm.call_args_list] == ["w1"]
    # El otro mensaje siguió al pipeline del bot (búsqueda del negocio por número).
    assert db.execute.await_count == 2


async def test_central_number_without_a_bot_keeps_everything_in_the_owner_channel(monkeypatch):
    hpm, db = await _webhook(monkeypatch, bot_on_number=False, owners={"+5215511111111"})
    assert [c.args[1]["id"] for c in hpm.call_args_list] == ["w1", "w2"]
    assert db.execute.await_count == 1
