#!/usr/bin/env python3
"""Prueba un prompt del backend con la IA de verdad (la misma cadena que usa
el bot), sin base de datos. Las pruebas normales simulan la IA: esto dice si
los textos funcionan con un modelo real.

Solo carga del backend/.env las llaves de IA (…API_KEY, …_BASE_URL, …_MODEL);
la base de datos apunta a un localhost falso, así que nunca toca producción.

Uso (desde la raíz del repo):
  backend/.venv/bin/python .claude/skills/nueva-funcion/scripts/probar_ia.py casos.json

casos.json:
{
  "system": "app.services.inbox_learning:_SUGGEST_SYSTEM",   # módulo:CONSTANTE o texto literal
  "max_tokens": 300,
  "cases": [
    {"input": "Cliente: ¿hacen envíos?\\nDueño: Sí, $30", "expect": "\\"useful\\": true", "forbid": ["Ana"]},
    {"input": "Cliente: gracias\\nDueño: a ti", "expect": "\\"useful\\": false"}
  ]
}
"""
import asyncio
import importlib
import json
import os
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[4] / "backend"


def load_llm_env() -> None:
    for line in (BACKEND / ".env").read_text().splitlines():
        key, _, value = line.strip().partition("=")
        if re.fullmatch(r"[A-Z_]*(API_KEY|API_TOKEN|ACCOUNT_ID|_BASE_URL|_MODEL)", key):
            os.environ[key] = value.strip().strip('"')
    if os.environ.get("USAR_OPENROUTER") != "1":
        # La llave local es la de producción y su cuota gratis (~50/día) es de los clientes reales.
        os.environ.pop("OPENROUTER_API_KEY", None)
    os.environ["APP_ENV_FILE"] = ""  # que app/config.py no lea el .env (producción)
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://u:p@localhost:1/none"
    os.environ.setdefault("SECRET_KEY", "probar-ia")
    sys.path.insert(0, str(BACKEND))


def resolve_system(value: str) -> str:
    if re.fullmatch(r"[\w.]+:[A-Za-z_]\w*", value):
        module, attr = value.split(":")
        return getattr(importlib.import_module(module), attr)
    return value


async def main(path: str) -> int:
    spec = json.loads(Path(path).read_text())
    load_llm_env()
    from app.services.llm_client import chat_completion

    system = resolve_system(spec["system"])
    failed = 0
    for i, case in enumerate(spec["cases"], 1):
        out = await chat_completion([{"role": "user", "content": case["input"]}], system=system,
                                    max_tokens=spec.get("max_tokens", 300), temperature=0)
        problems = []
        if case.get("expect") and case["expect"] not in out:
            problems.append(f"falta «{case['expect']}»")
        problems += [f"aparece «{w}»" for w in case.get("forbid", []) if w.lower() in out.lower()]
        failed += bool(problems)
        mark = "MAL" if problems else "OK "
        print(f"{mark} {i}. {case['input'][:60]!r} → {out[:160]!r}" + (f"  ({'; '.join(problems)})" if problems else ""))
    print(f"\n{len(spec['cases']) - failed}/{len(spec['cases'])} bien")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1])))
