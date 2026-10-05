"""Tests for app.services.llm_client — the provider-agnostic LLM adapter
(port of vocero-crm's src/lib/ai/index.ts pattern). Verifies the
Groq/OpenRouter/Anthropic chaining logic itself; individual call sites
(claude_service.py, banner_service.py, lab/judge.py, lab/simulator.py,
radio/scripts.py) mock chat_completion directly rather than re-testing
this branching in every file."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_client import (
    chat_completion,
    is_groq_configured,
    is_openrouter_configured,
)


def _base_settings() -> MagicMock:
    """Settings simulados con los proveedores nuevos apagados (Gemini,
    Mistral) y el tope de espera real; cada test prende lo que necesita."""
    s = MagicMock()
    s.CLOUDFLARE_ACCOUNT_ID = ""
    s.CLOUDFLARE_API_TOKEN = ""
    s.CLOUDFLARE_MODEL = ""
    s.GEMINI_API_KEY = ""
    s.GEMINI_MODEL = ""
    s.MISTRAL_API_KEY = ""
    s.MISTRAL_MODEL = ""
    s.OPENROUTER_JUDGE_MODEL = ""
    s.LLM_PROVIDER_TIMEOUT_SECONDS = 12.0
    return s


def _unconfigured_settings(mock_settings) -> None:
    """Baseline: no free provider configured — every test overrides only
    what it needs, so an untouched attribute never resolves to a truthy
    MagicMock and silently takes an unintended branch."""
    mock_settings.GROQ_API_KEY = ""
    mock_settings.GROQ_CHAT_MODEL = ""
    mock_settings.OPENROUTER_API_KEY = ""
    mock_settings.OPENROUTER_MODEL = ""
    mock_settings.OPENROUTER_JUDGE_MODEL = ""


class TestIsOpenrouterConfigured:
    def test_false_when_neither_set(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings:
            mock_settings.OPENROUTER_API_KEY = ""
            mock_settings.OPENROUTER_MODEL = ""
            assert is_openrouter_configured() is False

    def test_false_when_only_key_set(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "sk-or-test"
            mock_settings.OPENROUTER_MODEL = ""
            assert is_openrouter_configured() is False

    def test_false_when_only_model_set(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings:
            mock_settings.OPENROUTER_API_KEY = ""
            mock_settings.OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
            assert is_openrouter_configured() is False

    def test_true_when_both_set(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "sk-or-test"
            mock_settings.OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
            assert is_openrouter_configured() is True


class TestIsGroqConfigured:
    def test_false_when_neither_set(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings:
            mock_settings.GROQ_API_KEY = ""
            mock_settings.GROQ_CHAT_MODEL = ""
            assert is_groq_configured() is False

    def test_false_when_only_key_set(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings:
            mock_settings.GROQ_API_KEY = "gsk-test"
            mock_settings.GROQ_CHAT_MODEL = ""
            assert is_groq_configured() is False

    def test_true_when_both_set(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings:
            mock_settings.GROQ_API_KEY = "gsk-test"
            mock_settings.GROQ_CHAT_MODEL = "moonshotai/kimi-k2-instruct-0905"
            assert is_groq_configured() is True


class TestChatCompletionRoutesToAnthropicByDefault:
    @pytest.mark.asyncio
    async def test_uses_anthropic_when_nothing_else_configured(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings, \
             patch("app.services.llm_client._get_anthropic_client") as mock_get_anthropic, \
             patch("app.services.llm_client._get_groq_client") as mock_get_groq, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter:
            _unconfigured_settings(mock_settings)
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
        mock_get_groq.assert_not_called()
        mock_get_openrouter.assert_not_called()
        call_kwargs = anthropic_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-6"
        assert call_kwargs["system"] == "eres un asistente"

    @pytest.mark.asyncio
    async def test_anthropic_model_override_applies(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings, \
             patch("app.services.llm_client._get_anthropic_client") as mock_get_anthropic:
            _unconfigured_settings(mock_settings)
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

    @pytest.mark.asyncio
    async def test_force_anthropic_skips_groq_and_openrouter_even_when_configured(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings, \
             patch("app.services.llm_client._get_anthropic_client") as mock_get_anthropic, \
             patch("app.services.llm_client._get_groq_client") as mock_get_groq, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter:
            mock_settings.GROQ_API_KEY = "gsk-test"
            mock_settings.GROQ_CHAT_MODEL = "moonshotai/kimi-k2-instruct-0905"
            mock_settings.OPENROUTER_API_KEY = "sk-or-test"
            mock_settings.OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
            mock_settings.ANTHROPIC_MODEL = "claude-sonnet-4-6"

            anthropic_client = MagicMock()
            anthropic_response = MagicMock()
            anthropic_response.content = [MagicMock(text="respuesta confiable")]
            anthropic_client.messages.create = AsyncMock(return_value=anthropic_response)
            mock_get_anthropic.return_value = anthropic_client

            result = await chat_completion(
                [{"role": "user", "content": "hola"}], force_anthropic=True,
            )

        assert result == "respuesta confiable"
        mock_get_groq.assert_not_called()
        mock_get_openrouter.assert_not_called()


class TestChatCompletionRoutesToGroqWhenConfigured:
    @pytest.mark.asyncio
    async def test_uses_groq_when_configured(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings, \
             patch("app.services.llm_client._get_groq_client") as mock_get_groq, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter, \
             patch("app.services.llm_client._get_anthropic_client") as mock_get_anthropic:
            _unconfigured_settings(mock_settings)
            mock_settings.GROQ_API_KEY = "gsk-test"
            mock_settings.GROQ_CHAT_MODEL = "moonshotai/kimi-k2-instruct-0905"

            groq_client = MagicMock()
            groq_response = MagicMock()
            groq_response.choices = [MagicMock(message=MagicMock(content="respuesta de groq"))]
            groq_client.chat.completions.create = AsyncMock(return_value=groq_response)
            mock_get_groq.return_value = groq_client

            result = await chat_completion(
                [{"role": "user", "content": "hola"}], system="eres un asistente",
            )

        assert result == "respuesta de groq"
        mock_get_openrouter.assert_not_called()
        mock_get_anthropic.assert_not_called()
        call_kwargs = groq_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "moonshotai/kimi-k2-instruct-0905"
        assert call_kwargs["messages"][0] == {"role": "system", "content": "eres un asistente"}
        assert call_kwargs["messages"][1] == {"role": "user", "content": "hola"}

    @pytest.mark.asyncio
    async def test_groq_is_tried_before_openrouter(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings, \
             patch("app.services.llm_client._get_groq_client") as mock_get_groq, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter:
            mock_settings.GROQ_API_KEY = "gsk-test"
            mock_settings.GROQ_CHAT_MODEL = "moonshotai/kimi-k2-instruct-0905"
            mock_settings.OPENROUTER_API_KEY = "sk-or-test"
            mock_settings.OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"

            groq_client = MagicMock()
            groq_response = MagicMock()
            groq_response.choices = [MagicMock(message=MagicMock(content="respuesta de groq"))]
            groq_client.chat.completions.create = AsyncMock(return_value=groq_response)
            mock_get_groq.return_value = groq_client

            result = await chat_completion([{"role": "user", "content": "hola"}])

        assert result == "respuesta de groq"
        mock_get_openrouter.assert_not_called()


class TestChatCompletionFallsThroughOnProviderFailure:
    @pytest.mark.asyncio
    async def test_groq_failure_falls_back_to_openrouter(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings, \
             patch("app.services.llm_client._get_groq_client") as mock_get_groq, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter, \
             patch("app.services.llm_client._get_anthropic_client") as mock_get_anthropic:
            mock_settings.GROQ_API_KEY = "gsk-test"
            mock_settings.GROQ_CHAT_MODEL = "moonshotai/kimi-k2-instruct-0905"
            mock_settings.OPENROUTER_API_KEY = "sk-or-test"
            mock_settings.OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
            mock_settings.OPENROUTER_JUDGE_MODEL = ""

            groq_client = MagicMock()
            groq_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("429 rate limit"))
            mock_get_groq.return_value = groq_client

            or_client = MagicMock()
            or_response = MagicMock()
            or_response.choices = [MagicMock(message=MagicMock(content="respuesta gratis"))]
            or_client.chat.completions.create = AsyncMock(return_value=or_response)
            mock_get_openrouter.return_value = or_client

            result = await chat_completion([{"role": "user", "content": "hola"}])

        assert result == "respuesta gratis"
        mock_get_anthropic.assert_not_called()

    @pytest.mark.asyncio
    async def test_both_free_providers_failing_falls_back_to_anthropic(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings, \
             patch("app.services.llm_client._get_groq_client") as mock_get_groq, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter, \
             patch("app.services.llm_client._get_anthropic_client") as mock_get_anthropic:
            mock_settings.GROQ_API_KEY = "gsk-test"
            mock_settings.GROQ_CHAT_MODEL = "moonshotai/kimi-k2-instruct-0905"
            mock_settings.OPENROUTER_API_KEY = "sk-or-test"
            mock_settings.OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"
            mock_settings.OPENROUTER_JUDGE_MODEL = ""
            mock_settings.ANTHROPIC_MODEL = "claude-sonnet-4-6"

            groq_client = MagicMock()
            groq_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("429 rate limit"))
            mock_get_groq.return_value = groq_client

            or_client = MagicMock()
            or_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("429 rate limit"))
            mock_get_openrouter.return_value = or_client

            anthropic_client = MagicMock()
            anthropic_response = MagicMock()
            anthropic_response.content = [MagicMock(text="respuesta confiable")]
            anthropic_client.messages.create = AsyncMock(return_value=anthropic_response)
            mock_get_anthropic.return_value = anthropic_client

            result = await chat_completion(
                [{"role": "user", "content": "hola"}],
                anthropic_model="claude-haiku-4-5-20251001",
            )

        assert result == "respuesta confiable"
        assert anthropic_client.messages.create.call_args.kwargs["model"] == "claude-haiku-4-5-20251001"


class TestChatCompletionRoutesToOpenrouterWhenConfigured:
    @pytest.mark.asyncio
    async def test_uses_openrouter_when_configured(self):
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter, \
             patch("app.services.llm_client._get_anthropic_client") as mock_get_anthropic:
            _unconfigured_settings(mock_settings)
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
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter:
            _unconfigured_settings(mock_settings)
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
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter:
            _unconfigured_settings(mock_settings)
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
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter:
            _unconfigured_settings(mock_settings)
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
        with patch("app.services.llm_client.settings", new=_base_settings()) as mock_settings, \
             patch("app.services.llm_client._get_openrouter_client") as mock_get_openrouter:
            _unconfigured_settings(mock_settings)
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


class TestFreeProvidersFirstClaudeLast:
    """Decisión del dueño 2026-10-05: todos los gratis primero, Claude al final."""

    def _ok(self, text):
        client = MagicMock()
        client.chat.completions.create = AsyncMock(
            return_value=MagicMock(choices=[MagicMock(message=MagicMock(content=text))]))
        return client

    def _settings(self):
        s = _base_settings()
        s.GROQ_API_KEY, s.GROQ_CHAT_MODEL = "g", "openai/gpt-oss-120b"
        s.CLOUDFLARE_ACCOUNT_ID, s.CLOUDFLARE_API_TOKEN = "acc123", "cf"
        s.CLOUDFLARE_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
        s.GEMINI_API_KEY, s.GEMINI_MODEL = "ge", "gemini-2.5-flash-lite"
        s.MISTRAL_API_KEY, s.MISTRAL_MODEL = "mi", "mistral-small-latest"
        s.OPENROUTER_API_KEY, s.OPENROUTER_MODEL = "or", "a:free, b:free"
        s.ANTHROPIC_MODEL = "claude-haiku-4-5"
        return s

    @pytest.mark.asyncio
    async def test_order_empty_and_hung_providers_fall_through(self):
        groq = MagicMock()
        groq.chat.completions.create = AsyncMock(side_effect=TimeoutError("se atoró"))
        cloudflare = MagicMock()
        cloudflare.chat.completions.create = AsyncMock(side_effect=RuntimeError("sin neuronas"))
        gemini = self._ok("")  # vacío = falla
        mistral = MagicMock()
        mistral.chat.completions.create = AsyncMock(side_effect=RuntimeError("429"))
        openrouter = MagicMock()
        openrouter.chat.completions.create = AsyncMock(side_effect=[
            RuntimeError("modelo a sin cupo"),
            MagicMock(choices=[MagicMock(message=MagicMock(content="hola desde b"))]),
        ])
        anthropic_client = MagicMock()
        with patch("app.services.llm_client.settings", new=self._settings()), \
             patch("app.services.llm_client._get_groq_client", return_value=groq), \
             patch("app.services.llm_client._get_cloudflare_client", return_value=cloudflare), \
             patch("app.services.llm_client._get_gemini_client", return_value=gemini), \
             patch("app.services.llm_client._get_mistral_client", return_value=mistral), \
             patch("app.services.llm_client._get_openrouter_client", return_value=openrouter), \
             patch("app.services.llm_client._get_anthropic_client", return_value=anthropic_client):
            out = await chat_completion([{"role": "user", "content": "hola"}])
        assert out == "hola desde b"
        assert [c.kwargs["model"] for c in openrouter.chat.completions.create.call_args_list] == ["a:free", "b:free"]
        assert groq.chat.completions.create.call_args.kwargs["timeout"] == 12.5  # 500 tokens / 40
        cloudflare.chat.completions.create.assert_awaited_once()  # va después de Groq
        anthropic_client.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_claude_answers_when_every_free_one_fails(self):
        dead = MagicMock()
        dead.chat.completions.create = AsyncMock(side_effect=RuntimeError("caído"))
        anthropic_client = MagicMock()
        anthropic_client.messages.create = AsyncMock(return_value=MagicMock(content=[MagicMock(text="respaldo")]))
        with patch("app.services.llm_client.settings", new=self._settings()), \
             patch("app.services.llm_client._get_groq_client", return_value=dead), \
             patch("app.services.llm_client._get_cloudflare_client", return_value=dead), \
             patch("app.services.llm_client._get_gemini_client", return_value=dead), \
             patch("app.services.llm_client._get_mistral_client", return_value=dead), \
             patch("app.services.llm_client._get_openrouter_client", return_value=dead), \
             patch("app.services.llm_client._get_anthropic_client", return_value=anthropic_client):
            out = await chat_completion([{"role": "user", "content": "hola"}])
        assert out == "respaldo"
        assert dead.chat.completions.create.await_count == 6  # groq, cloudflare, gemini, mistral, 2 de openrouter
        assert anthropic_client.messages.create.call_args.kwargs["timeout"] == 25.0


    @pytest.mark.asyncio
    async def test_leaked_reasoning_is_not_sent_to_the_customer(self):
        thinker = self._ok("Here's a thinking process:\n\n1. Analyze...")
        tagged = self._ok("<think>el cliente quiere cita</think>¡Claro! ¿Qué día te acomoda?")
        with patch("app.services.llm_client.settings", new=self._settings()), \
             patch("app.services.llm_client._get_groq_client", return_value=thinker), \
             patch("app.services.llm_client._get_gemini_client", return_value=tagged):
            out = await chat_completion([{"role": "user", "content": "quiero cita"}])
        assert out == "¡Claro! ¿Qué día te acomoda?"


def test_cloudflare_url_uses_the_account():
    from app.services import llm_client

    with patch("app.services.llm_client.settings", new=_base_settings()) as s:
        s.CLOUDFLARE_ACCOUNT_ID, s.CLOUDFLARE_API_TOKEN = "acc123", "tok"
        llm_client._openai_clients.pop("cloudflare", None)
        client = llm_client._get_cloudflare_client()
        llm_client._openai_clients.pop("cloudflare", None)
    assert str(client.base_url).rstrip("/") == "https://api.cloudflare.com/client/v4/accounts/acc123/ai/v1"
