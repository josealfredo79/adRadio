"""
Adaptador de proveedor LLM intercambiable — ÚNICA frontera con el proveedor
de IA para generación de texto (port del patrón de vocero-crm's
src/lib/ai/index.ts). Todo el código que antes llamaba a
anthropic.AsyncAnthropic().messages.create(...) directamente ahora pasa por
chat_completion() aquí.

Cadena de proveedores (cada uno opcional vía variables de entorno): Groq →
OpenRouter → Anthropic. Groq y OpenRouter comparten el formato de chat
completions de OpenAI, así que reutilizan el cliente `openai` que el
proyecto ya trae para Whisper. Si un proveedor gratis falla (cuota agotada,
error de red, etc.) se intenta el siguiente automáticamente — Anthropic es
el fallback pagado final y confiable. Si ninguno de Groq/OpenRouter está
configurado, cae directo en Anthropic — el comportamiento que este proyecto
tuvo siempre, sin cambios de default.
"""
import logging

import anthropic
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_anthropic_client: anthropic.AsyncAnthropic | None = None
_openrouter_client: AsyncOpenAI | None = None
_groq_client: AsyncOpenAI | None = None


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


def _get_groq_client() -> AsyncOpenAI:
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url=settings.GROQ_CHAT_BASE_URL,
        )
    return _groq_client


def is_openrouter_configured() -> bool:
    return bool(settings.OPENROUTER_API_KEY and settings.OPENROUTER_MODEL)


def is_groq_configured() -> bool:
    return bool(settings.GROQ_API_KEY and settings.GROQ_CHAT_MODEL)


async def _openai_compatible_completion(
    client: AsyncOpenAI, model: str, messages: list[dict],
    system: str | None, max_tokens: int, temperature: float,
) -> str:
    or_messages = ([{"role": "system", "content": system}] if system else []) + messages
    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=or_messages,
    )
    return (response.choices[0].message.content or "").strip()


async def chat_completion(
    messages: list[dict],
    *,
    system: str | None = None,
    max_tokens: int = 500,
    temperature: float = 0.3,
    anthropic_model: str | None = None,
    judge: bool = False,
    force_anthropic: bool = False,
) -> str:
    """Genera una respuesta de chat con el proveedor configurado.

    `messages` son turnos {"role": "user"|"assistant", "content": ...} sin
    el system prompt (va aparte en `system`, como en la API de Anthropic —
    para OpenRouter se antepone como mensaje role="system", el formato
    estándar de OpenAI).

    `anthropic_model` sobreescribe el modelo SOLO en la rama Anthropic (ej.
    Haiku para el bot por costo, en vez del ANTHROPIC_MODEL default) — no
    aplica en Groq/OpenRouter, porque ahí el modelo se elige por variable de
    entorno, no por función que llama (esa es la simplicidad del patrón: un
    solo modelo configurado, no uno hardcodeado por caso de uso). `judge=True`
    usa OPENROUTER_JUDGE_MODEL si está configurado (si no, cae en
    OPENROUTER_MODEL) — solo aplica en la rama OpenRouter.

    `force_anthropic=True` salta las ramas Groq y OpenRouter aunque estén
    configuradas — para un call site puntual que necesita un fallback
    confiable (no gratis), sin cambiar el proveedor default de todo el
    proyecto.

    Cadena: si no se pidió `force_anthropic`, se intenta primero Groq (si
    está configurado) y luego OpenRouter (si está configurado) — un error de
    cualquiera de los dos (cuota agotada, red, etc.) cae automáticamente al
    siguiente en la cadena, terminando en Anthropic si ambos fallan.
    """
    if not force_anthropic:
        if is_groq_configured():
            try:
                return await _openai_compatible_completion(
                    _get_groq_client(), settings.GROQ_CHAT_MODEL,
                    messages, system, max_tokens, temperature,
                )
            except Exception as e:
                logger.warning("[LLM] Groq falló, probando siguiente proveedor: %s", e)

        if is_openrouter_configured():
            model = (settings.OPENROUTER_JUDGE_MODEL or settings.OPENROUTER_MODEL) if judge else settings.OPENROUTER_MODEL
            try:
                return await _openai_compatible_completion(
                    _get_openrouter_client(), model,
                    messages, system, max_tokens, temperature,
                )
            except Exception as e:
                logger.warning("[LLM] OpenRouter falló, usando Anthropic: %s", e)

    client = _get_anthropic_client()
    response = await client.messages.create(
        model=anthropic_model or settings.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system or anthropic.NOT_GIVEN,
        messages=messages,
    )
    return response.content[0].text.strip()
