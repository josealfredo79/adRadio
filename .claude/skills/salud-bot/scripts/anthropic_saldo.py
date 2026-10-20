#!/usr/bin/env python3
"""¿Le queda saldo a la cuenta de Anthropic de producción? (solo lectura)

Anthropic no tiene una API para ver el saldo: cuando se acaba, cada llamada
contesta 400 "Your credit balance is too low". Este script toma la llave de
producción de Railway (solo en memoria, nunca la imprime) y hace la llamada más
barata posible (Haiku, 1 token de respuesta, menos de un centavo) para saberlo.

Uso: anthropic_saldo.py   → sale con 0 si hay saldo, 1 si no, 2 si no se pudo revisar
"""
import json
import subprocess
import sys
import urllib.error
import urllib.request


def prod_vars() -> dict[str, str]:
    out = subprocess.run(["railway", "variables", "-s", "adRadio", "--kv"], capture_output=True,
                         text=True, timeout=60, stdin=subprocess.DEVNULL).stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def main() -> int:
    env = prod_vars()
    key = env.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("⚠️  No encontré ANTHROPIC_API_KEY en Railway (adRadio): no se pudo revisar.")
        return 2
    model = env.get("CUSTOMER_AGENT_MODEL", "").strip() or "claude-haiku-4-5"
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({"model": model, "max_tokens": 1,
                         "messages": [{"role": "user", "content": "ok"}]}).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            print(f"✅ Anthropic con saldo ({model} contestó).")
            return 0
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        msg = json.loads(body).get("error", {}).get("message", body) if body.startswith("{") else body
        if "credit balance" in msg.lower():
            print("🔴 Anthropic SIN SALDO: el último respaldo del bot, del agente del cliente y del Copiloto no "
                  "funciona. Recarga en console.anthropic.com → Settings → Billing.")
            return 1
        if e.code == 401:
            print("🔴 La llave de Anthropic de producción no es válida (401).")
            return 1
        print(f"⚠️  Anthropic contestó {e.code}: {msg[:200]}")
        return 2
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"⚠️  No se pudo llegar a Anthropic: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
