#!/usr/bin/env bash
# PostToolUse (Edit|Write): corre `ruff check` sobre el .py del backend recién
# editado, para que el error salga aquí y no en CI. Solo avisa (exit 2 le
# muestra el error a Claude); no corrige ni formatea nada.
file=$(jq -r '.tool_input.file_path // empty')
case "$file" in
  */backend/*.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

backend="${CLAUDE_PROJECT_DIR:-$(pwd)}/backend"
ruff="$backend/.venv/bin/ruff"
[ -x "$ruff" ] || ruff=$(command -v ruff) || exit 0

if ! out=$(cd "$backend" && "$ruff" check --quiet "$file" 2>&1); then
  echo "ruff encontró problemas en $file (CI fallaría):" >&2
  echo "$out" >&2
  exit 2
fi
