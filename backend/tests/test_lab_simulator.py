"""Tests for app.services.lab.simulator — mocked LLM calls, no real API."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.lab.personas import PERSONAS
from app.services.lab.simulator import generate_persona_message, run_persona_conversation


class TestGeneratePersonaMessage:
    @pytest.mark.asyncio
    async def test_first_message_has_no_history_instruction(self):
        persona = PERSONAS[0]
        with patch(
            "app.services.lab.simulator.chat_completion",
            new=AsyncMock(return_value="Hola, quiero comprar."),
        ) as mock_chat:
            msg = await generate_persona_message(persona, {"business_name": "Tacos El Primo"}, [])
        assert msg == "Hola, quiero comprar."
        call_args = mock_chat.call_args
        assert "primer mensaje" in call_args.args[0][0]["content"]

    @pytest.mark.asyncio
    async def test_subsequent_message_includes_transcript(self):
        persona = PERSONAS[0]
        history = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "¡Hola! ¿En qué te ayudo?"},
        ]
        with patch(
            "app.services.lab.simulator.chat_completion",
            new=AsyncMock(return_value="¿Y el precio?"),
        ) as mock_chat:
            msg = await generate_persona_message(persona, {"business_name": "Tacos El Primo"}, history)
        assert msg == "¿Y el precio?"
        prompt_text = mock_chat.call_args.args[0][0]["content"]
        assert "Hola" in prompt_text
        assert "¡Hola! ¿En qué te ayudo?" in prompt_text


class TestRunPersonaConversation:
    @pytest.mark.asyncio
    async def test_stops_at_end_marker(self, mock_db, test_user):
        persona = PERSONAS[0]
        with patch(
            "app.services.lab.simulator.generate_persona_message", new=AsyncMock(return_value="***FIN***")
        ):
            transcript = await run_persona_conversation(persona, test_user, mock_db)
        assert transcript == []

    @pytest.mark.asyncio
    async def test_full_conversation_alternates_roles(self, mock_db, test_user):
        persona = PERSONAS[0]
        persona_msgs = iter(["Hola quiero comprar", "Sí confirmo", "***FIN***"])
        bot_msgs = iter(["¡Hola! ¿Qué te gustaría?", "Perfecto, pedido confirmado"])

        async def _fake_persona(*args, **kwargs):
            return next(persona_msgs)

        async def _fake_rag(**kwargs):
            return next(bot_msgs)

        with patch("app.services.lab.simulator.generate_persona_message", new=_fake_persona), \
             patch("app.services.lab.simulator.answer_with_rag", new=_fake_rag):
            transcript = await run_persona_conversation(persona, test_user, mock_db)

        assert len(transcript) == 4
        assert [m["role"] for m in transcript] == ["user", "assistant", "user", "assistant"]
        assert transcript[0]["content"] == "Hola quiero comprar"
        assert transcript[3]["content"] == "Perfecto, pedido confirmado"

    @pytest.mark.asyncio
    async def test_respects_max_turns(self, mock_db, test_user):
        persona = PERSONAS[0]
        with patch(
            "app.services.lab.simulator.generate_persona_message",
            new=AsyncMock(return_value="sigo preguntando"),
        ), patch(
            "app.services.lab.simulator.answer_with_rag",
            new=AsyncMock(return_value="respuesta del bot"),
        ):
            transcript = await run_persona_conversation(persona, test_user, mock_db)
        assert len(transcript) == persona.max_turns * 2

    @pytest.mark.asyncio
    async def test_rag_failure_produces_error_placeholder_not_crash(self, mock_db, test_user):
        persona = PERSONAS[0]
        with patch(
            "app.services.lab.simulator.generate_persona_message",
            new=AsyncMock(side_effect=["hola", "***FIN***"]),
        ), patch(
            "app.services.lab.simulator.answer_with_rag",
            new=AsyncMock(side_effect=Exception("claude down")),
        ):
            transcript = await run_persona_conversation(persona, test_user, mock_db)
        assert transcript[1]["content"] == "[ERROR: el bot no pudo responder]"

    @pytest.mark.asyncio
    async def test_never_imports_messaging_send_functions(self):
        """Structural guardrail: the sandbox must not be able to send real WhatsApp messages."""
        import app.services.lab.simulator as sim
        source_globals = set(sim.__dict__.keys())
        assert "send_whatsapp" not in source_globals
        assert "meta_service" not in source_globals
        assert "twilio_service" not in source_globals
