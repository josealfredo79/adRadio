---
name: deploy
description: Subir cambios de adradio/IaRadio a producción de forma segura y verificada — pruebas, commit, push a master (Railway despliega web, worker y beat solos) y confirmación de que los tres servicios quedaron en el commit nuevo y producción responde. Úsalo siempre que el usuario diga "despliega", "súbelo", "pásalo a producción", "haz push", "ya súbelo", o al terminar una función con la skill nueva-funcion y él apruebe subirla.
---

# Deploy (IaRadio)

Producción tiene clientes reales y **no hay staging**: lo que se sube a `master` lo ven ellos en minutos. Este flujo existe para que nada suba sin pruebas y para confirmar de verdad que quedó arriba, no solo que el push funcionó.

## 1. Qué se sube

- `git status` y `git diff --stat`. Separa **tus** cambios de los que el usuario ya tenía sin commit: solo agrega por nombre los archivos que tú cambiaste (nunca `git add -A` ni `.`). Si hay cambios ajenos, menciónalos y déjalos fuera.
- Si hay migraciones nuevas en `backend/alembic/versions/`, avisa: corren solas al arrancar web (`start.sh`), y si fallan, web no arranca. Revisa que la migración sea reversible y no borre datos.

## 2. Pruebas

- Backend, si se tocó `backend/`: desde `backend/`, `PATH="$PWD/.venv/bin:$PATH" scripts/test_local.sh` (Docker local, ~2.5 min; nunca contra Neon).
- Frontend, si se tocó `frontend/`: desde `frontend/`, `npx tsc --noEmit -p .`, `npx eslint <archivos tocados>`, `npx vitest run`.
- Solo corre la parte que se tocó. Si la suite ya pasó en esta sesión con exactamente este código (nada cambió después salvo docs), no la repitas: dilo en el reporte.
- Si algo falla, no se sube. Arregla o reporta la falla con la salida real.
- Si el diff toca Stripe, pagos, planes o cuotas, Cobrar, cupones, campañas o envíos de WhatsApp, y el subagente `revisor-dinero` no lo revisó ya en esta sesión, lánzalo ahora. Con "No subir", no se sube.

## 3. Confirmar con el usuario

Push a `master` es publicar a clientes. Si el usuario no pidió explícitamente subir en este mismo turno, pregúntale con `AskUserQuestion` ("Subir a producción (Recomendado)" / "Todavía no"), con un resumen de una línea de qué cambia para sus clientes.

## 4. Commit y push

Mensaje en inglés, primera línea corta con el qué, cuerpo con el porqué. Termina con la línea de atribución que indique el sistema. Luego `git push origin master`.

## 5. Verificar el despliegue

Corre `bash .claude/skills/deploy/scripts/check_deploy.sh <sha>` (en segundo plano si quieres, tarda 2 a 6 min). El script espera a que **adRadio (web), worker y beat** estén en SUCCESS con ese commit y luego revisa `/health` y `/health/ready`.

- Si un servicio falla: `railway logs -s <servicio> --deployment` y reporta la causa real.
- Si se pasa de tiempo o muestra `ERROR_CLI` (la herramienta de Railway a veces no responde un rato, o la máquina se suspendió): revisa `railway deployment list -s <servicio> --limit 3` antes de concluir nada; casi siempre el despliegue sí terminó.
- Después de un cambio al bot, corre `python3 .claude/skills/revisar-prod/scripts/prod_logs.py --since 30m` unos minutos después para ver que no salgan errores nuevos.

## 6. Reporte

Dile al usuario en pocas líneas: commit, que los tres servicios quedaron arriba y producción responde, y la **prueba real** que le toca hacer (pasos concretos). Si el cambio no se puede probar del todo sin él (su teléfono, esperar un tiempo, aprobación de Meta), dilo claro: subido no es lo mismo que probado.
