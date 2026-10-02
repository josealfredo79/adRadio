"""'Habla con IaRadio' (POST /copilot/voice): el dueño le habla al Copiloto.

Lo crítico: la voz va al mismo Copiloto (con respuestas para decirse en voz
alta), y una acción pendiente solo se ejecuta con un "sí" claro — si no queda
claro, es una petición nueva y la acción NO se ejecuta."""
import json
import uuid
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers
from starlette.requests import Request

from app.api.v1.copilot import voice
from app.models.user import User
from app.services.copilot_service import _build_system_prompt, parse_spoken_yes_no

REPLY = {"reply": "Tienes 3 citas hoy.", "actions": [], "pending_confirmation": None}


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/copilot/voice", "headers": [],
                    "client": (f"test-{uuid.uuid4()}", 1), "query_string": b""})


def _user() -> User:
    return User(id=uuid.uuid4(), email="dueno@iaradio.online", password_hash="x", business_name="Barbería Don Pepe")


async def _call(**form):
    args = {"audio": None, "text": None, "history": None, "confirmation_id": None, "photo_url": None, **form}
    return await voice(request=_request(), db=None, current_user=_user(), redis=None, **args)


class TestSpokenYesNo:
    @pytest.mark.parametrize("said", ["Sí", "sí, hazlo", "Claro que sí", "dale", "Ándale pues", "va, mándala", "OK"])
    def test_yes(self, said):
        assert parse_spoken_yes_no(said) is True

    @pytest.mark.parametrize("said", ["No", "no, cancela", "mejor no", "todavía no", "Espera"])
    def test_no(self, said):
        assert parse_spoken_yes_no(said) is False

    @pytest.mark.parametrize("said", [
        "sí pero no a todos",  # dijo las dos cosas
        "¿cuántas citas tengo mañana?",  # otra petición
        "sí, y luego créame un cupón del diez por ciento para los clientes nuevos de la semana",  # demasiado largo
    ])
    def test_unclear_is_not_an_answer(self, said):
        assert parse_spoken_yes_no(said) is None


class TestVoiceEndpoint:
    @pytest.mark.asyncio
    async def test_audio_is_transcribed_and_goes_to_the_copilot_in_voice_mode(self):
        whisper = AsyncMock(return_value="¿Cuántas citas tengo hoy?")
        chat = AsyncMock(return_value=REPLY)
        audio = UploadFile(file=BytesIO(b"webm"), filename="nota.webm", headers=Headers({"content-type": "audio/webm"}))
        history = json.dumps([{"role": "user", "content": "hola"}, {"role": "assistant", "content": "¡Hola!"}])
        with patch("app.api.v1.voice_setup.transcribe_audio_bytes", whisper), patch("app.api.v1.copilot.handle_chat", chat):
            out = await _call(audio=audio, history=history)
        assert out.transcript == "¿Cuántas citas tengo hoy?"
        assert out.reply == "Tienes 3 citas hoy."
        args = chat.await_args
        assert args.args[2] == "¿Cuántas citas tengo hoy?"
        assert args.args[3] == [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "¡Hola!"}]
        assert args.kwargs["channel"] == "voz"

    @pytest.mark.asyncio
    async def test_clear_yes_confirms_the_pending_action(self):
        confirm = AsyncMock(return_value={"reply": "Listo, la campaña ya salió.", "actions": [], "pending_confirmation": None})
        chat = AsyncMock(return_value=REPLY)
        with patch("app.api.v1.copilot.handle_confirm", confirm), patch("app.api.v1.copilot.handle_chat", chat):
            out = await _call(text="sí, hazlo", confirmation_id="tok")
        assert confirm.await_args.args[2:4] == ("tok", True)
        assert confirm.await_args.kwargs["channel"] == "voz"
        chat.assert_not_awaited()
        assert out.reply == "Listo, la campaña ya salió."

    @pytest.mark.asyncio
    async def test_clear_no_cancels(self):
        confirm = AsyncMock(return_value={"reply": "Entendido, no hice ningún cambio.", "actions": [], "pending_confirmation": None})
        with patch("app.api.v1.copilot.handle_confirm", confirm):
            await _call(text="no, mejor no", confirmation_id="tok")
        assert confirm.await_args.args[2:4] == ("tok", False)

    @pytest.mark.asyncio
    async def test_anything_else_is_a_new_request_and_does_not_run_the_action(self):
        confirm = AsyncMock()
        chat = AsyncMock(return_value=REPLY)
        with patch("app.api.v1.copilot.handle_confirm", confirm), patch("app.api.v1.copilot.handle_chat", chat):
            await _call(text="¿y cuántos clientes tengo?", confirmation_id="tok")
        confirm.assert_not_awaited()
        assert chat.await_args.args[2] == "¿y cuántos clientes tengo?"


def test_voice_prompt_asks_for_speakable_answers():
    prompt = _build_system_prompt(_user(), "voz")
    assert "en voz alta" in prompt and "Nada de listas" in prompt
    assert "en voz alta" not in _build_system_prompt(_user())


@pytest.mark.asyncio
async def test_own_photo_goes_with_the_message_and_foreign_ones_do_not():
    chat = AsyncMock(return_value=REPLY)
    user = _user()
    own = f"https://x/api/v1/radio/audio/products/{user.id}/a.jpg"
    with patch("app.api.v1.copilot.handle_chat", chat):
        await voice(request=_request(), audio=None, text="agrega este producto, tinte a 450", history=None,
                    confirmation_id=None, photo_url=own, db=None, current_user=user, redis=None)
        assert chat.await_args.args[2] == f"agrega este producto, tinte a 450\n[Foto adjunta: {own}]"
        await voice(request=_request(), audio=None, text="agrega este", history=None, confirmation_id=None,
                    photo_url="https://evil.example/x.jpg", db=None, current_user=user, redis=None)
        assert chat.await_args.args[2] == "agrega este"
