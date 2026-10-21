# IaRadio (repo adradio)

Asistente de WhatsApp + web para negocios chicos de México (Tlaxiaco y alrededores). El dueño
configura su bot, el cliente final platica por WhatsApp o por la web del negocio (`/sitio`, `/mi`).
Producción tiene **clientes reales y no hay staging**.

El usuario escribe en español sencillo: contéstale igual, sin jerga técnica innecesaria.

## Stack

- **backend/**: FastAPI + SQLAlchemy async + Alembic, Celery + Redis, Postgres en Neon (pgvector).
  `app/services/` (lógica), `app/domain/` (acciones compartidas por canal), `app/workers/` (Celery),
  `app/api/v1/` (rutas).
- **frontend/**: React + Vite + TypeScript + Tailwind. Páginas en `src/pages/`.
- **Railway**: tres servicios desde `master` — `adRadio` (web, corre `alembic upgrade head` al
  arrancar vía `start.sh`), `worker` y `beat`. Un push a `master` los redespliega a los tres.
- IA: cadena de modelos gratis primero y Claude al final (`app/services/llm_client.py`);
  embeddings con Voyage.

## Reglas que no se rompen

- **`backend/.env` es PRODUCCIÓN (Neon).** `app/config.py` lo lee por defecto: cualquier script,
  `alembic` o `uvicorn` corrido en local sin entorno propio escribe en la base real. Para local:
  `set -a; . backend/.env.test; set +a; export APP_ENV_FILE=""`. Un hook lo bloquea
  (`.claude/hooks/guard_bash.py`).
- **Producción solo la toca el usuario**, con `! <comando>` en el prompt. Nada de `railway run`,
  ni Celery `.delay` desde local. Logs de producción (solo lectura): skill `revisar-prod`.
- **El repo es PÚBLICO** (github.com/josealfredo79/adRadio). Nunca subir `.env`, respaldos,
  documentos `.docx`, datos de clientes ni capturas con contraseñas. `git add` siempre por nombre.
- Nunca concluir el estado de producción a partir de la config local (las llaves locales pueden
  ser viejas).

## Pruebas

- Backend: desde `backend/`, `PATH="$PWD/.venv/bin:$PATH" scripts/test_local.sh [args de pytest]`
  (Postgres y Redis en Docker, base nueva en cada corrida; `tests/conftest.py` bloquea Neon).
- Frontend: desde `frontend/`, `npx tsc --noEmit -p .`, `npx eslint <archivos>`, `npx vitest run`.
- Prompts del bot contra un modelo real: `.claude/skills/nueva-funcion/scripts/probar_ia.py`.
- Lint: `ruff check` (CI fija ruff 0.16.10). Un hook lo corre en cada `.py` editado. No uses
  `ruff format`: el código no está formateado con él y ensuciaría los diffs.

## Cómo trabajamos

- Funciones nuevas o cambios grandes → skill `nueva-funcion` (spec en `docs/specs/`, aprobación
  con botones, una prueba por caso). Arreglos chicos y claros → directo.
- Subir a producción → skill `deploy` (pruebas, push, `check_deploy.sh` verifica los tres
  servicios). Subido no es lo mismo que probado: siempre decir qué prueba real le toca al usuario.
- Subagentes del proyecto (`.claude/agents/`): `cliente-simulado` (platica con el bot real en una
  base local desechable) y `revisor-dinero` (revisa diffs que tocan cobros o mensajes que Meta cobra).
  Cambios a la base → skill `migracion`.
- Verificación profunda: pruebas end-to-end con infraestructura real, no solo que compile.
- Commits en inglés, primera línea corta con el qué y cuerpo con el porqué.
- Migraciones: deben ser reversibles y no borrar datos; si fallan, la web no arranca.

## Producto (criterios del dueño)

- El cliente final **toca botones en vez de escribir** siempre que se pueda.
- WhatsApp es el anzuelo, la web es donde se resuelve (cuesta menos que mensajes de Meta).
- "Cobrar" es solo monto + quién; **no es un punto de venta**. Mejoras solo si quitan trabajo.
- Montos en pesos se escriben `$5`, no `$5.00`.
- El bot no inventa canales, precios ni servicios: si no está en la base de conocimiento, no existe.
