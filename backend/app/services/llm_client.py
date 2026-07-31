"""
Adaptador de proveedor LLM intercambiable — ÚNICA frontera con el proveedor
de IA para generación de texto (port del patrón de vocero-crm's
src/lib/ai/index.ts). Todo el código que antes llamaba a
anthropic.AsyncAnthropic().messages.create(...) directamente ahora pasa por
chat_completion() aquí.

Si OPENROUTER_API_KEY y OPENROUTER_MODEL están configurados, se usa
OpenRouter (compatible con el formato de chat completions de OpenAI, así
que reutiliza el cliente `openai` que el proyecto ya trae para Whisper) —
esto permite cambiar de modelo, incluyendo modelos gratis, con solo una
variable de entorno. Si no, cae en Anthropic directo — el comportamiento
que este proyecto tuvo siempre, sin cambios de default.
"""
import logging

import anthropic
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_anthropic_client: anthropic.AsyncAnthropic | None = None
_openrouter_client: AsyncOpenAI | None = None


def _get_anthropic_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic_client


def _get_openrouter_client() -> AsyncOpenAI:
    global _openrouter_client
    if _openrouter_client is None:
        _openrouter_client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
        )
    return _openrouter_client


def is_openrouter_configured() -> bool:
    return bool(settings.OPENROUTER_API_KEY and settings.OPENROUTER_MODEL)


async def chat_completion(
    messages: list[dict],
    *,
    system: str | None = None,
    max_tokens: int = 500,
    temperature: float = 0.3,
    anthropic_model: str | None = None,
    judge: bool = False,
) -> str:
    """Genera una respuesta de chat con el proveedor configurado.

    `messages` son turnos {"role": "user"|"assistant", "content": ...} sin
    el system prompt (va aparte en `system`, como en la API de Anthropic —
    para OpenRouter se antepone como mensaje role="system", el formato
    estándar de OpenAI).

    `anthropic_model` sobreescribe el modelo SOLO en la rama Anthropic (ej.
    Haiku para el bot por costo, en vez del ANTHROPIC_MODEL default) — no
    aplica si OpenRouter está activo, porque ahí el modelo se elige por
    variable de entorno, no por función que llama (esa es la simplicidad
    del patrón: un solo modelo configurado, no uno hardcodeado por caso de
    uso). `judge=True` usa OPENROUTER_JUDGE_MODEL si está configurado
    (si no, cae en OPENROUTER_MODEL) — solo aplica con OpenRouter activo.
    """
    if is_openrouter_configured():
        client = _get_openrouter_client()
        model = (settings.OPENROUTER_JUDGE_MODEL or settings.OPENROUTER_MODEL) if judge else settings.OPENROUTER_MODEL
        or_messages = ([{"role": "system", "content": system}] if system else []) + messages
        response = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=or_messages,
        )
        return (response.choices[0].message.content or "").strip()

    client = _get_anthropic_client()
    response = await client.messages.create(
        model=anthropic_model or settings.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system or anthropic.NOT_GIVEN,
        messages=messages,
    )
    return response.content[0].text.strip()
