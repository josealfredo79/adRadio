"""Tests for app.services.llm_client — the provider-agnostic LLM adapter
(port of vocero-crm's src/lib/ai/index.ts pattern). Verifies the
Anthropic/OpenRouter branching logic itself; individual call sites
(claude_service.py, banner_service.py, lab/judge.py, lab/simulator.py,
radio/scripts.py) mock chat_completion directly rather than re-testing
this branching in every file."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_client import chat_completion, is_openrouter_configured


class TestIsOpenrouterConfigured:
    def test_false_when_neither_set(self):
        with patch("app.services.llm_client.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = ""
            mock_settings.OPENROUTER_MODEL = ""
            assert is_openrouter_configured() is False

    def test_false_when_only_key_set(self):
        with patch("app.services.llm_client.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "sk-or-test"
            mock_settings.OPENROUTER_MODEL = ""
            assert is_openrouter_configured() is False

    def test_false_when_only_model_set(self):
        with patch("app.services.llm_client.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = ""
            mock_settings.OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
            assert is_openrouter_configured() is False

    def test_true_when_both_set(self):
        with patch("app.services.llm_client.settings") as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "sk-or-test"
            mock_settings.OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
            assert is_openrouter_configured() is True


class TestChatCompletionRoutesToAnthropicByDefault:
    @pytest.mark.asyncio
    async def test_uses_anthropic_when_openrouter_not_configured(self):
        with patch("app.services.llm_client.settings") as mock_settings, \
             patch("app.services.llm_client._get_anthropic_client") as mock_get_anthropic, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter:
            mock_settings.OPENROUTER_API_KEY = ""
            mock_settings.OPENROUTER_MODEL = ""
            mock_settings.ANTHROPIC_MODEL = "claude-sonnet-4-6"

            anthropic_client = MagicMock()
            anthropic_response = MagicMock()
            anthropic_response.content = [MagicMock(text="respuesta de claude")]
            anthropic_client.messages.create = AsyncMock(return_value=anthropic_response)
            mock_get_anthropic.return_value = anthropic_client

            result = await chat_completion(
                [{"role": "user", "content": "hola"}], system="eres un asistente",
            )

        assert result == "respuesta de claude"
        mock_get_openrouter.assert_not_called()
        call_kwargs = anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-6"
        assert call_kwargs["system"] == "eres un asistente"

    @pytest.mark.asyncio
    async def test_anthropic_model_override_applies(self):
        with patch("app.services.llm_client.settings") as mock_settings, \
             patch("app.services.llm_client._get_anthropic_client") as mock_get_anthropic:
            mock_settings.OPENROUTER_API_KEY = ""
            mock_settings.OPENROUTER_MODEL = ""
            mock_settings.ANTHROPIC_MODEL = "claude-sonnet-4-6"

            anthropic_client = MagicMock()
            anthropic_response = MagicMock()
            anthropic_response.content = [MagicMock(text="ok")]
            anthropic_client.messages.create = AsyncMock(return_value=anthropic_response)
            mock_get_anthropic.return_value = anthropic_client

            await chat_completion(
                [{"role": "user", "content": "hola"}],
                anthropic_model="claude-haiku-4-5-20251001",
            )

        assert anthropic_client.messages.create.call_args.kwargs["model"] == "claude-haiku-4-5-20251001"


class TestChatCompletionRoutesToOpenrouterWhenConfigured:
    @pytest.mark.asyncio
    async def test_uses_openrouter_when_configured(self):
        with patch("app.services.llm_client.settings") as mock_settings, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter, \
             patch("app.services.llm_client._get_anthropic_client") as mock_get_anthropic:
            mock_settings.OPENROUTER_API_KEY = "sk-or-test"
            mock_settings.OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
            mock_settings.OPENROUTER_JUDGE_MODEL = ""

            or_client = MagicMock()
            or_response = MagicMock()
            or_response.choices = [MagicMock(message=MagicMock(content="respuesta gratis"))]
            or_client.chat.completions.create = AsyncMock(return_value=or_response)
            mock_get_openrouter.return_value = or_client

            result = await chat_completion(
                [{"role": "user", "content": "hola"}], system="eres un asistente",
            )

        assert result == "respuesta gratis"
        mock_get_anthropic.assert_not_called()
        call_kwargs = or_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "meta-llama/llama-3.1-8b-instruct:free"
        assert call_kwargs["messages"][0] == {"role": "system", "content": "eres un asistente"}
        assert call_kwargs["messages"][1] == {"role": "user", "content": "hola"}

    @pytest.mark.asyncio
    async def test_anthropic_model_override_is_ignored_on_openrouter(self):
        """anthropic_model only applies to the Anthropic branch — OpenRouter
        always uses the configured OPENROUTER_MODEL, the whole point being
        one model chosen via env var, not one hardcoded per call site."""
        with patch("app.services.llm_client.settings") as mock_settings, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter:
            mock_settings.OPENROUTER_API_KEY = "sk-or-test"
            mock_settings.OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
            mock_settings.OPENROUTER_JUDGE_MODEL = ""

            or_client = MagicMock()
            or_response = MagicMock()
            or_response.choices = [MagicMock(message=MagicMock(content="ok"))]
            or_client.chat.completions.create = AsyncMock(return_value=or_response)
            mock_get_openrouter.return_value = or_client

            await chat_completion(
                [{"role": "user", "content": "hola"}],
                anthropic_model="claude-haiku-4-5-20251001",
            )

        assert or_client.chat.completions.create.call_args.kwargs["model"] == "meta-llama/llama-3.1-8b-instruct:free"

    @pytest.mark.asyncio
    async def test_judge_flag_uses_judge_model_when_set(self):
        with patch("app.services.llm_client.settings") as mock_settings, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter:
            mock_settings.OPENROUTER_API_KEY = "sk-or-test"
            mock_settings.OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
            mock_settings.OPENROUTER_JUDGE_MODEL = "anthropic/claude-3-5-haiku"

            or_client = MagicMock()
            or_response = MagicMock()
            or_response.choices = [MagicMock(message=MagicMock(content="veredicto"))]
            or_client.chat.completions.create = AsyncMock(return_value=or_response)
            mock_get_openrouter.return_value = or_client

            await chat_completion([{"role": "user", "content": "evalúa esto"}], judge=True)

        assert or_client.chat.completions.create.call_args.kwargs["model"] == "anthropic/claude-3-5-haiku"

    @pytest.mark.asyncio
    async def test_judge_flag_falls_back_to_main_model_when_judge_model_unset(self):
        with patch("app.services.llm_client.settings") as mock_settings, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter:
            mock_settings.OPENROUTER_API_KEY = "sk-or-test"
            mock_settings.OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
            mock_settings.OPENROUTER_JUDGE_MODEL = ""

            or_client = MagicMock()
            or_response = MagicMock()
            or_response.choices = [MagicMock(message=MagicMock(content="veredicto"))]
            or_client.chat.completions.create = AsyncMock(return_value=or_response)
            mock_get_openrouter.return_value = or_client

            await chat_completion([{"role": "user", "content": "evalúa esto"}], judge=True)

        assert or_client.chat.completions.create.call_args.kwargs["model"] == "meta-llama/llama-3.1-8b-instruct:free"

    @pytest.mark.asyncio
    async def test_no_system_prompt_does_not_add_system_message(self):
        with patch("app.services.llm_client.settings") as mock_settings, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter:
            mock_settings.OPENROUTER_API_KEY = "sk-or-test"
            mock_settings.OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
            mock_settings.OPENROUTER_JUDGE_MODEL = ""

            or_client = MagicMock()
            or_response = MagicMock()
            or_response.choices = [MagicMock(message=MagicMock(content="ok"))]
            or_client.chat.completions.create = AsyncMock(return_value=or_response)
            mock_get_openrouter.return_value = or_client

            await chat_completion([{"role": "user", "content": "hola"}])

        sent_messages = or_client.chat.completions.create.call_args.kwargs["messages"]
        assert sent_messages == [{"role": "user", "content": "hola"}]
