"""
Adaptador de proveedor LLM intercambiable — ÚNICA frontera con el proveedor
de IA para generación de texto (port del patrón de vocero-crm's
src/lib/ai/index.ts). Todo el código que antes llamaba a
anthropic.AsyncAnthropic().messages.create(...) directamente ahora pasa por
chat_completion() aquí.

Cadena (decisión del dueño 2026-10-05: primero todos los gratis, Claude al
final): Groq → Gemini → Mistral → OpenRouter (uno o varios modelos) →
Anthropic. Cada proveedor es opcional: sin llave se salta. Todos los gratis
hablan el formato de chat completions de OpenAI, así que comparten el
cliente `openai`. Si uno falla — error, cuota agotada, se atora más de
LLM_PROVIDER_TIMEOUT_SECONDS o contesta vacío — se pasa al siguiente.
Anthropic es el respaldo pagado final y confiable.
"""
import logging
import re
from collections.abc import Callable

import anthropic
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_anthropic_client: anthropic.AsyncAnthropic | None = None
_openai_clients: dict[str, AsyncOpenAI] = {}


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_LEAKED_REASONING = re.compile(r"^(<think>|here'?s (a|my) thinking process|\*\*analy[sz]e|okay, (so|let me)|let me think)",
                               re.IGNORECASE)


class EmptyReply(Exception):
    """El proveedor contestó sin texto: cuenta como falla y se prueba el siguiente."""


def _timeout(max_tokens: int, base: float) -> float:
    # Textos largos (guiones de radio, banners) necesitan más que un mensaje de chat.
    return max(base, max_tokens / 40)


def _get_anthropic_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=1)
    return _anthropic_client


def _client(name: str, api_key: str, base_url: str) -> AsyncOpenAI:
    if name not in _openai_clients:
        # Sin reintentos del SDK: si falla, mejor pasar ya al siguiente proveedor.
        _openai_clients[name] = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0)
    return _openai_clients[name]


def _get_groq_client() -> AsyncOpenAI:
    return _client("groq", settings.GROQ_API_KEY, settings.GROQ_CHAT_BASE_URL)


def _get_gemini_client() -> AsyncOpenAI:
    return _client("gemini", settings.GEMINI_API_KEY, settings.GEMINI_BASE_URL)


def _get_mistral_client() -> AsyncOpenAI:
    return _client("mistral", settings.MISTRAL_API_KEY, settings.MISTRAL_BASE_URL)


def _get_openrouter_client() -> AsyncOpenAI:
    return _client("openrouter", settings.OPENROUTER_API_KEY, settings.OPENROUTER_BASE_URL)


def is_groq_configured() -> bool:
    return bool(settings.GROQ_API_KEY and settings.GROQ_CHAT_MODEL)


def is_gemini_configured() -> bool:
    return bool(settings.GEMINI_API_KEY and settings.GEMINI_MODEL)


def is_mistral_configured() -> bool:
    return bool(settings.MISTRAL_API_KEY and settings.MISTRAL_MODEL)


def is_openrouter_configured() -> bool:
    return bool(settings.OPENROUTER_API_KEY and settings.OPENROUTER_MODEL)


def _models(value: str) -> list[str]:
    return [m.strip() for m in (value or "").split(",") if m.strip()]


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
        timeout=_timeout(max_tokens, settings.LLM_PROVIDER_TIMEOUT_SECONDS),
    )
    text = (response.choices[0].message.content or "").strip() if response.choices else ""
    # Modelos gratis que "piensan": a veces devuelven su razonamiento en vez de
    # la respuesta (visto 2026-10-05 en OpenRouter). Eso no se le manda al cliente.
    text = _THINK_RE.sub("", text).strip()
    if not text or _LEAKED_REASONING.match(text):
        raise EmptyReply(model)
    return text


def free_chain(judge: bool = False, economy: bool = False) -> list[tuple[str, Callable[[], bool], Callable]]:
    """Los proveedores gratis en orden: (nombre, ¿configurado?, fábrica de
    llamada). La fábrica recibe (messages, system, max_tokens, temperature)."""

    def make(get_client: Callable[[], AsyncOpenAI], models: Callable[[], list[str]]):
        async def call(messages, system, max_tokens, temperature) -> str:
            last: Exception | None = None
            for model in models():
                try:
                    return await _openai_compatible_completion(get_client(), model, messages, system,
                                                               max_tokens, temperature)
                except Exception as e:  # el siguiente modelo del mismo proveedor
                    last = e
            raise last or EmptyReply("sin modelo")
        return call

    openrouter_models = (
        (lambda: _models(settings.OPENROUTER_JUDGE_MODEL or settings.OPENROUTER_MODEL)) if judge
        else (lambda: _models(settings.OPENROUTER_MODEL))
    )
    chain = [
        ("Groq", is_groq_configured, make(_get_groq_client, lambda: [settings.GROQ_CHAT_MODEL])),
        ("Gemini", is_gemini_configured, make(_get_gemini_client, lambda: [settings.GEMINI_MODEL])),
        ("Mistral", is_mistral_configured, make(_get_mistral_client, lambda: [settings.MISTRAL_MODEL])),
        ("OpenRouter", is_openrouter_configured, make(_get_openrouter_client, openrouter_models)),
    ]
    if economy:
        # Negocio que ya pasó la cuota de su plan (plan_usage.py): primero el
        # modelo gratis de OpenRouter, para no gastar la cuota de los demás.
        chain.sort(key=lambda p: p[0] != "OpenRouter")
    return chain


async def chat_completion(
    messages: list[dict],
    *,
    system: str | None = None,
    max_tokens: int = 500,
    temperature: float = 0.3,
    anthropic_model: str | None = None,
    judge: bool = False,
    force_anthropic: bool = False,
    economy: bool = False,
) -> str:
    """Genera una respuesta de chat: prueba los proveedores gratis en orden y
    termina en Anthropic.

    `messages` son turnos {"role": "user"|"assistant", "content": ...} sin
    el system prompt (va aparte en `system`, como en la API de Anthropic;
    para los proveedores compatibles con OpenAI se antepone como
    role="system").

    `anthropic_model` sobreescribe el modelo SOLO en la rama Anthropic (ej.
    Haiku para el bot por costo). `judge=True` usa OPENROUTER_JUDGE_MODEL si
    está configurado. `economy=True` prueba primero OpenRouter.
    `force_anthropic=True` salta los gratis — para un call site que necesita
    el respaldo confiable.
    """
    if not force_anthropic:
        for name, configured, call in free_chain(judge=judge, economy=economy):
            if not configured():
                continue
            try:
                return await call(messages, system, max_tokens, temperature)
            except Exception as e:
                logger.warning("[LLM] %s falló, probando siguiente proveedor: %s", name, e)

    response = await _get_anthropic_client().messages.create(
        model=anthropic_model or settings.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system or anthropic.NOT_GIVEN,
        messages=messages,
        timeout=_timeout(max_tokens, 25.0),
    )
    text = "".join(b.text for b in response.content if isinstance(getattr(b, "text", None), str)).strip()
    if not text:
        raise EmptyReply(anthropic_model or settings.ANTHROPIC_MODEL)
    return text

