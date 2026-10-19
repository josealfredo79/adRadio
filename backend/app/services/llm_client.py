"""
Adaptador de proveedor LLM intercambiable — ÚNICA frontera con el proveedor
de IA para generación de texto (port del patrón de vocero-crm's
src/lib/ai/index.ts). Todo el código que antes llamaba a
anthropic.AsyncAnthropic().messages.create(...) directamente ahora pasa por
chat_completion() aquí.

Cadena (decisión del dueño 2026-10-05: primero todos los gratis, Claude al
final): Groq → Cloudflare → Gemini → Mistral → OpenRouter (uno o varios modelos) →
Anthropic. Cada proveedor es opcional: sin llave se salta. Todos los gratis
hablan el formato de chat completions de OpenAI, así que comparten el
cliente `openai`. Si uno falla — error, cuota agotada, se atora más de
LLM_PROVIDER_TIMEOUT_SECONDS o contesta vacío — se pasa al siguiente.
Anthropic es el respaldo pagado final y confiable.
"""
import json
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

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


def _get_cloudflare_client() -> AsyncOpenAI:
    base = f"https://api.cloudflare.com/client/v4/accounts/{settings.CLOUDFLARE_ACCOUNT_ID}/ai/v1"
    return _client("cloudflare", settings.CLOUDFLARE_API_TOKEN, base)


def _get_gemini_client() -> AsyncOpenAI:
    return _client("gemini", settings.GEMINI_API_KEY, settings.GEMINI_BASE_URL)


def _get_mistral_client() -> AsyncOpenAI:
    return _client("mistral", settings.MISTRAL_API_KEY, settings.MISTRAL_BASE_URL)


def _get_openrouter_client() -> AsyncOpenAI:
    return _client("openrouter", settings.OPENROUTER_API_KEY, settings.OPENROUTER_BASE_URL)


def is_groq_configured() -> bool:
    return bool(settings.GROQ_API_KEY and settings.GROQ_CHAT_MODEL)


def is_cloudflare_configured() -> bool:
    return bool(settings.CLOUDFLARE_ACCOUNT_ID and settings.CLOUDFLARE_API_TOKEN and settings.CLOUDFLARE_MODEL)


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

    return [(name, configured, make(get_client, models))
            for name, configured, get_client, models in _free_providers(judge, economy)]


def _free_providers(judge: bool = False, economy: bool = False) -> list[tuple]:
    """(nombre, ¿configurado?, cliente, modelos) de cada proveedor gratis, en orden."""
    openrouter_models = (
        (lambda: _models(settings.OPENROUTER_JUDGE_MODEL or settings.OPENROUTER_MODEL)) if judge
        else (lambda: _models(settings.OPENROUTER_MODEL))
    )
    chain = [
        ("Groq", is_groq_configured, _get_groq_client, lambda: [settings.GROQ_CHAT_MODEL]),
        ("Cloudflare", is_cloudflare_configured, _get_cloudflare_client, lambda: [settings.CLOUDFLARE_MODEL]),
        ("Gemini", is_gemini_configured, _get_gemini_client, lambda: [settings.GEMINI_MODEL]),
        ("Mistral", is_mistral_configured, _get_mistral_client, lambda: [settings.MISTRAL_MODEL]),
        ("OpenRouter", is_openrouter_configured, _get_openrouter_client, openrouter_models),
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



# ─── Con herramientas (Copiloto) ──────────────────────────────────────────────
# El historial va en formato Anthropic (bloques text / tool_use / tool_result
# como dicts) y se traduce al de OpenAI para cada gratis. Así, si a media
# vuelta un proveedor falla y entra otro, el historial le sirve igual y no se
# repiten herramientas ya ejecutadas.

@dataclass
class ToolCall:
    id: str
    name: str
    input: dict
    error: str | None = None  # argumentos que no eran JSON válido
    extra: dict | None = None  # campos propios del proveedor que hay que devolverle tal cual


@dataclass
class ToolReply:
    text: str
    tool_calls: list[ToolCall]
    content: list[dict] = field(default_factory=list)  # bloques para el historial
    provider: str = ""


def _openai_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                               "parameters": t["input_schema"]}} for t in tools]


def _to_openai_messages(messages: list[dict], system: str | None) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}] if system else []
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
            continue
        texts = [b["text"] for b in content if b.get("type") == "text" and b.get("text")]
        if m["role"] == "assistant":
            calls = [{"id": b["id"], "type": "function",
                      "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False)},
                      **(b.get("openai_extra") or {})}
                     for b in content if b.get("type") == "tool_use"]
            msg: dict = {"role": "assistant", "content": "\n".join(texts) or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
            continue
        for b in content:
            if b.get("type") == "tool_result":
                out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b.get("content") or ""})
        if texts:
            out.append({"role": "user", "content": "\n".join(texts)})
    return out


def _parse_tool_call(call) -> ToolCall:
    raw = call.function.arguments or ""
    call_id = call.id or f"call_{uuid.uuid4().hex[:12]}"
    try:
        args = json.loads(raw) if raw.strip() else {}
    except ValueError:
        args = None
    # Gemini 3 manda una firma (extra_content.google.thought_signature) con
    # cada llamada y rechaza la siguiente vuelta si no se la regresan.
    extra = {k: v for k, v in (getattr(call, "model_extra", None) or {}).items() if k == "extra_content"} or None
    if not isinstance(args, dict):
        return ToolCall(call_id, call.function.name, {}, error=f"Argumentos inválidos (no es JSON): {raw[:200]}",
                        extra=extra)
    return ToolCall(call_id, call.function.name, args, extra=extra)


async def _openai_tool_completion(client: AsyncOpenAI, model: str, messages: list[dict], system: str | None,
                                  tools: list[dict], max_tokens: int, temperature: float) -> ToolReply:
    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=_to_openai_messages(messages, system),
        tools=_openai_tools(tools),
        timeout=_timeout(max_tokens, settings.LLM_PROVIDER_TIMEOUT_SECONDS),
    )
    msg = response.choices[0].message if response.choices else None
    text = _THINK_RE.sub("", (msg.content or "") if msg else "").strip()
    calls = [_parse_tool_call(c) for c in ((msg.tool_calls or []) if msg else [])]
    if not calls and (not text or _LEAKED_REASONING.match(text)):
        raise EmptyReply(model)
    content = ([{"type": "text", "text": text}] if text else []) + [
        {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input, **({"openai_extra": c.extra} if c.extra else {})}
        for c in calls]
    return ToolReply(text, calls, content)


# Probado 2026-10-18 con las herramientas del Copiloto y llaves de producción:
# Gemini acertó 7/7 (y lee bien los resultados); Groq acierta pero su tope por
# minuto se acaba con 1–2 mensajes del Copiloto (las herramientas pesan) y es
# el mismo tope del bot de los clientes, así que va después; Llama 3.3 de
# Cloudflare elige la herramienta equivocada y manda "null" como texto: sigue
# en la cadena de texto del bot, no en la de herramientas.
_NO_TOOLS = {"Cloudflare"}
_TOOLS_FIRST = "Gemini"


def _for_anthropic(messages: list[dict]) -> list[dict]:
    """Quita del historial los campos de otros proveedores (Anthropic los rechaza)."""
    def clean(content):
        if isinstance(content, str):
            return content
        return [{k: v for k, v in b.items() if k != "openai_extra"} for b in content]
    return [{**m, "content": clean(m["content"])} for m in messages]


async def tool_completion(
    messages: list[dict],
    *,
    system: str | None,
    tools: list[dict],
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> ToolReply:
    """Como chat_completion pero con herramientas: gratis primero (Gemini a la
    cabeza, ver _TOOLS_FIRST), Anthropic al final. `tools` en formato
    Anthropic (name/description/input_schema)."""
    providers = sorted(_free_providers(), key=lambda p: p[0] != _TOOLS_FIRST)
    for name, configured, get_client, models in providers:
        if name in _NO_TOOLS or not configured():
            continue
        for model in models():
            try:
                reply = await _openai_tool_completion(get_client(), model, messages, system, tools,
                                                      max_tokens, temperature)
                reply.provider = name
                return reply
            except Exception as e:
                logger.warning("[LLM] %s (%s) con herramientas falló, probando siguiente: %s", name, model, e)

    # Las herramientas no cambian entre llamadas: con la marca de caché en la
    # última, Anthropic cobra ~10% por ellas en cada vuelta.
    cached_tools = [*tools[:-1], {**tools[-1], "cache_control": {"type": "ephemeral"}}] if tools else []
    response = await _get_anthropic_client().messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system or anthropic.NOT_GIVEN,
        tools=cached_tools,
        messages=_for_anthropic(messages),
        # Además cachea hasta el último mensaje: las vueltas siguientes del
        # mismo turno reusan instrucciones e historial.
        cache_control={"type": "ephemeral"},
        timeout=_timeout(max_tokens, 25.0),
    )
    content: list[dict] = []
    calls: list[ToolCall] = []
    for b in response.content:
        if getattr(b, "type", None) == "text" and b.text.strip():
            content.append({"type": "text", "text": b.text})
        elif getattr(b, "type", None) == "tool_use":
            calls.append(ToolCall(b.id, b.name, b.input or {}))
            content.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input or {}})
    text = "\n".join(b["text"].strip() for b in content if b["type"] == "text")
    return ToolReply(text, calls, content, provider="Anthropic")
