"""Prueba modelos gratis de OpenRouter: ¿responden, usan herramientas, español limpio?
Uso: python3 .claude/skills/salud-bot/scripts/openrouter_modelos.py <modelo:free> [...]
Cada modelo gasta 2 llamadas de la cuota diaria gratis (compartida si la llave local es la de producción)."""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

KEY = next(l.split("=", 1)[1].strip().strip('"') for l in
           Path("/home/josealfredo/adradio/backend/.env").read_text().splitlines()
           if l.startswith("OPENROUTER_API_KEY="))
TOOLS = [{"type": "function", "function": {
    "name": "horarios_libres", "description": "Horarios libres de un día para una cita.",
    "parameters": {"type": "object", "properties": {"fecha": {"type": "string", "description": "AAAA-MM-DD"}},
                   "required": ["fecha"]}}}]
SYSTEM = ("Eres el asistente de Estética Lupita en Tlaxiaco. Hoy es martes 2026-10-20. "
          "Usa las herramientas para datos del negocio. Contesta en español de México, breve.")


def call(model, messages, tools=True):
    body = {"model": model, "messages": [{"role": "system", "content": SYSTEM}, *messages], "max_tokens": 400}
    if tools:
        body["tools"] = TOOLS
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", json.dumps(body).encode(),
                                 {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} {e.read()[:120]!r}", time.time() - t
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}", time.time() - t
    if "error" in data:
        return None, str(data["error"])[:120], time.time() - t
    return data["choices"][0]["message"], None, time.time() - t


for model in sys.argv[1:]:
    msg, err, secs = call(model, [{"role": "user", "content": "tienen lugar mañana pa un corte?"}])
    if err:
        print(f"❌ {model}: {err} ({secs:.1f}s)")
        continue
    calls = msg.get("tool_calls") or []
    tool_ok = bool(calls) and calls[0]["function"]["name"] == "horarios_libres"
    args = calls[0]["function"]["arguments"] if calls else ""
    msg2, err2, secs2 = call(model, [{"role": "user", "content": "el tinte me quedó mal, quiero hablar con alguien"}],
                             tools=False)
    reply = (msg2 or {}).get("content") or err2 or ""
    junk = bool(re.search(r"[一-鿿]|\b(perfectly|sorry|the|you)\b", reply, re.I))
    print(f"{'✅' if tool_ok and not junk and not err2 else '⚠️'} {model}: herramienta={tool_ok} {args} "
          f"({secs:.1f}s) | texto{' CON BASURA' if junk else ''} ({secs2:.1f}s): {reply[:110]!r}")
