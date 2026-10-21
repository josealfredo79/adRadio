---
name: migracion
description: Crear y probar una migración de Alembic de IaRadio sin poner en riesgo producción — numeración manual (0077, 0078…), probada subiendo, bajando y volviendo a subir en Postgres local, sin borrar datos y compatible con el código viejo mientras Railway despliega. Úsalo siempre que un cambio agregue o modifique tablas, columnas, índices o datos en la base (modelos en backend/app/models/), aunque el usuario no diga "migración".
---

# Migración (IaRadio)

La web corre `alembic upgrade head` contra **Neon producción** al arrancar (`start.sh`). Si la migración falla, **la web no arranca** y se cae todo, incluida la landing. No hay staging: lo que pruebes en local es la única red.

## 1. Escribirla

- A mano en `backend/alembic/versions/NNNN_nombre_corto.py`, con el número siguiente al último (`ls backend/alembic/versions | sort | tail -1`). `revision = "NNNN"`, `down_revision = "<anterior>"`.
- Docstring en español: qué hace y por qué, con la spec si hay (`docs/specs/...`). Copia el estilo de la última.
- Cambia el modelo en `backend/app/models/` igual que la migración (mismos tipos, `server_default`, índices).
- `downgrade()` real que deshaga todo. Si de verdad no se puede, dilo en el docstring y avísale al usuario.

## 2. Reglas para no tumbar producción

Web, worker y beat se despliegan casi al mismo tiempo, y por unos minutos **el código viejo corre contra la base nueva**. Por eso:
- **Solo aditiva en un despliegue:** tablas nuevas, columnas `nullable=True` o con `server_default`. Nunca `NOT NULL` sin default sobre una tabla con filas.
- **Borrar o renombrar va en dos despliegues:** primero el código deja de usar la columna; en un despliegue posterior, la migración la quita.
- **Datos:** un `UPDATE` masivo dentro de la migración bloquea la tabla en Neon. Si son muchas filas, hazlo por lotes o en una tarea aparte. Nunca `DELETE` de datos de clientes sin que el usuario lo apruebe explícitamente.
- **Índices** en tablas grandes (`messages`, `contacts`, `conversations`): `postgresql_concurrently=True` dentro de `with op.get_context().autocommit_block():`.
- `pgvector` y JSONB ya están; no cambies dimensiones de `Vector(1024)` (los embeddings de Voyage dependen de eso).

## 3. Probarla en local (obligatorio)

Desde `backend/`, contra el Postgres de Docker de las pruebas (nunca Neon; el hook `guard_bash.py` bloquea alembic sin `.env.test`):

```bash
cd backend
PATH="$PWD/.venv/bin:$PATH" scripts/test_local.sh -x -q tests/test_health_ready.py   # Postgres limpio en 55432, migra a head
set -a; . ./.env.test; set +a; export APP_ENV_FILE=""
.venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head   # baja y vuelve a subir
.venv/bin/alembic current                                  # debe decir NNNN (head)
.venv/bin/alembic check 2>&1 | grep -i "<tu_tabla>"        # vacío = modelo y migración coinciden
```

`alembic check` sin filtro siempre falla: el repo ya trae diferencias viejas entre modelos y base (sobre todo índices creados en migraciones que los modelos no declaran, y la tabla vieja `pool_numbers`). Solo importa lo de las tablas que tocaste. No las "arregles" de paso en tu migración.

Luego corre la suite completa (`scripts/test_local.sh`): las pruebas usan el esquema migrado.

Si la migración toca datos existentes, siembra antes filas parecidas a las de producción (con `NULL`, vacías, viejas) y comprueba que sobreviven.

## 4. Desplegar

- Usa la skill `deploy`. En el reporte para el usuario di que hay migración y qué cambia.
- Después del push, `check_deploy.sh` confirma que web arrancó, lo que significa que la migración pasó. Si web falla: `railway logs -s adRadio --deployment` y busca el error de alembic.
- **Emergencia** (la base falla y la web no arranca): `SKIP_MIGRATIONS=true` en Railway levanta la web sin migrar. Es temporal; quítala en cuanto se arregle. Ver `ROLLBACK.md`.
- `alembic downgrade` contra producción **solo lo corre el usuario** con `!`, y solo si la migración rompió datos. Para una migración aditiva basta revertir el código.
