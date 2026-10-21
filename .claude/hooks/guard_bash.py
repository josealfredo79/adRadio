#!/usr/bin/env python3
"""PreToolUse (Bash): frena dos accidentes que ya pasaron o que saldrían caros.

1. Correr código del backend en local sin entorno propio: app/config.py lee
   backend/.env, que es Neon PRODUCCIÓN (pasó 2026-10-04: semillas en prod).
2. `git add` masivo o de archivos sensibles: el repo es público.

Los comandos que el usuario corre con "!" no pasan por aquí, a propósito:
ese es el camino para tocar producción.
"""

import json
import re
import sys

# Comandos que cargan app/config.py (y por tanto backend/.env).
LOADS_APP = re.compile(
    r"\balembic\s+(upgrade|downgrade|revision|stamp|current|history|heads|merge|check)\b"
    r"|\buvicorn\s+app\."
    r"|\bcelery\b.*\s-A\s+app\b"
    r"|\bpython[\d.]*\s+(-\S+\s+)*(\S*/)?scripts/\w+\.py"
    r"|\bpython[\d.]*\s+(-\S+\s+)*-m\s+app\b"
    r"|\bpython[\d.]*\s+(-\S+\s+)*-c\s+.*\b(from|import)\s+app\b"
)
# Señales de que el comando ya apunta a otra base o no lee backend/.env.
LOCAL_ENV = re.compile(
    r"APP_ENV_FILE=|\.env\.test\b|test_local\.sh"
    r"|DATABASE_URL=\S*(localhost|127\.0\.0\.1)"
)
# Scripts que ya se protegen solos (ponen APP_ENV_FILE="" y una base falsa) o
# que no cargan la app.
SAFE_SCRIPTS = re.compile(r"\.claude/skills/\S+/scripts/\w+\.py")

# Solo "git add" en posición de comando: no dentro de un `-m "..."`.
GIT_ADD = re.compile(r"(?:^|[;&|(]\s*)git\s+add\b([^;&|\n]*)", re.MULTILINE)
GIT_ADD_ALL = re.compile(r"(^|\s)(-A|--all|-f|--force|\.|:/|\*)(\s|$)")
SENSITIVE = re.compile(
    r"(\.env(\.[\w.-]+)?(?<!\.example)(\s|$)|\.docx?\b|\.sql\b|\.dump\b|\.pem\b|\.key\b"
    r"|Zone\.Identifier|backup|credentials|secret)",
    re.IGNORECASE,
)


HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1.*?\n\2\s*$", re.DOTALL | re.MULTILINE)


def code_only(cmd: str) -> str:
    """El comando sin el cuerpo de sus heredocs (mensajes de commit, contenido
    de archivos): ahí "git add -A" o "alembic" son texto, no comandos."""
    return HEREDOC.sub("", cmd)


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    raw = (data.get("tool_input") or {}).get("command") or ""
    cmd = code_only(raw)

    without_safe = SAFE_SCRIPTS.sub("", cmd)
    if LOADS_APP.search(without_safe) and not LOCAL_ENV.search(cmd):
        deny(
            "Bloqueado: este comando carga app/config.py, que lee backend/.env = Neon "
            "PRODUCCIÓN. Para local, antepón: `set -a; . ./.env.test; set +a; "
            "export APP_ENV_FILE=\"\";` (desde backend/) o usa scripts/test_local.sh. "
            "Si de verdad hay que tocar producción, pídele al usuario que lo corra con "
            "`! <comando>`."
        )

    for match in GIT_ADD.finditer(cmd):
        args = match.group(1)
        if GIT_ADD_ALL.search(args):
            deny(
                "Bloqueado: el repo es PÚBLICO. Agrega los archivos por nombre "
                "(nada de `git add -A`, `.`, `-f` ni comodines)."
            )
        if SENSITIVE.search(args):
            deny(
                "Bloqueado: el repo es PÚBLICO y esto parece un archivo sensible "
                "(.env, .docx, respaldo, llave o Zone.Identifier). Pregúntale al usuario "
                "antes de subirlo."
            )


if __name__ == "__main__":
    main()
