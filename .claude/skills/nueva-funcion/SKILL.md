---
name: nueva-funcion
description: Flujo rápido de "especificación → plan → construir → probar" para funciones nuevas o cambios grandes de IaRadio/adradio. Úsalo siempre que el usuario pida algo nuevo o un cambio que toque varios archivos, varios canales (WhatsApp, web, Inbox, portal) o dinero/mensajes cobrados por Meta — aunque no diga "especificación" ni "/nueva-funcion" (p. ej. "quiero que el bot haga X", "agrega una bandeja de…", "que el cliente pueda…"). No lo uses para arreglos chicos y claros (un texto, un color, un error puntual): esos se hacen directo.
---

# Nueva función (IaRadio)

El usuario es el dueño de IaRadio: decide **qué** se construye; tú decides **cómo**. Este flujo existe para que lo que construyas sea lo que él planeó, sin hacerlo escribir documentos largos ni perder tiempo. Toda la plática con él es en español sencillo, sin jerga.

La meta de velocidad: de su idea a un plan aprobado en **dos rondas de botones** como máximo.

## 0. ¿Toca este flujo?

Si el cambio es chico y claro (un texto, un estilo, un error con causa obvia, un solo archivo), no uses este flujo: hazlo directo. El flujo cuesta minutos; úsalo cuando equivocarse cueste más que eso (varios archivos, varios canales, clientes reales, dinero, WhatsApp/Meta).

## 1. Entiende antes de preguntar (sin preguntarle nada aún)

Lee el código que se tocaría y las memorias del proyecto relacionadas. Así tus preguntas serán sobre decisiones de negocio reales, no cosas que el código ya responde. Busca en especial:
- qué ya existe y se puede reusar (servicios en `backend/app/services/`, componentes en `frontend/src/components/`),
- qué canales toca (WhatsApp cobrado por Meta, web gratis, Inbox del dueño, portal `/c/`),
- riesgos conocidos: producción sin staging, costo de mensajes de Meta, plantillas que requieren aprobación, workers de Celery.

## 2. Pregunta con botones (una sola ronda)

Usa `AskUserQuestion` con **2 a 4 preguntas en una sola llamada**. El usuario prefiere tocar a escribir. Cada pregunta:
- es una decisión que solo él puede tomar (quién lo ve, qué pasa en el caso raro, si va por WhatsApp o web, si arranca apagado),
- trae opciones concretas, con la recomendada primero y marcada "(Recomendado)",
- explica en la descripción de cada opción qué implica en la práctica (costo, riesgo, lo que ve el cliente).

No preguntes lo que puedes decidir tú con criterio técnico ni lo que ya dijo. Si ya está todo claro, sáltate esta ronda.

## 3. Escribe la especificación

Guárdala en `docs/specs/AAAA-MM-DD-<nombre-corto>.md` usando la plantilla de `assets/plantilla-spec.md`. Lo central son los **casos**: cada uno es una frase verificable "Si …, entonces …" escrita como la diría el dueño. Esos casos son el contrato: cada uno tendrá su prueba.

Incluye siempre "Fuera de alcance" (lo que NO se hará ahora): evita que el trabajo crezca sin que él lo decida.

## 4. Aprobación (segunda y última ronda)

Muéstrale en el chat un resumen corto: los casos numerados y el plan en 3 a 6 viñetas (qué se cambia, en palabras de negocio; los archivos van en la especificación, no en el chat). Luego `AskUserQuestion` con: "Aprobar y construir (Recomendado)" / "Cambiar algo". Si cambia algo, ajusta la especificación y vuelve a mostrar solo lo que cambió.

No escribas código de la función antes de esta aprobación.

## 5. Construye, un caso a la vez

- Escribe la prueba de cada caso (nómbrala para que se reconozca el caso) y luego el código que la hace pasar.
- Backend: pruebas con base y Redis reales vía `backend/scripts/test_local.sh` (necesita `PATH="$PWD/.venv/bin:$PATH"` desde `backend/`). Mockea solo APIs externas de pago (Claude, Meta, TTS, Stripe, R2), nunca la base ni Redis.
- Frontend: `npx tsc --noEmit -p .`, `npx eslint <archivos>`, `npx vitest run` desde `frontend/`.
- Lo riesgoso (cobra, manda WhatsApp masivo, cambia cómo contesta el bot a todos) arranca detrás de una bandera apagada, salvo que el usuario haya elegido otra cosa.
- Nunca corras scripts contra producción desde local: `backend/.env` apunta a producción. Si necesitas datos de producción, escribe un script de solo lectura en el scratchpad y dale al usuario la línea con `!` para correrlo.

## 5b. Prueba con la IA de verdad (si la función usa prompts)

Las pruebas simulan la IA, así que no dicen si tus textos funcionan con un modelo real. Arma 5 a 10 casos realistas (incluye los difíciles: datos personales, respuestas ambiguas) y córrelos con `scripts/probar_ia.py` (instrucciones dentro; nunca toca la base de producción). Si falla alguno, ajusta el prompt antes de entregar y anota el resultado en la especificación.

Si el cambio toca lo que el cliente vive en el chat (agente del cliente, citas, pedidos, catálogo, respuestas del bot), además lanza el subagente `cliente-simulado`: platica con el bot completo por el chat web real (`scripts/simular_cliente.py`, base local desechable) y reporta fallas verificadas. Si toca dinero o mensajes que Meta cobra, lanza el subagente `revisor-dinero` sobre el diff antes de entregar. Si toca la base, sigue la skill `migracion`.

## 6. Cierra contra la especificación

Marca en la especificación cada caso con ✅ y el nombre de su prueba (o ❌ y por qué). Reporta al usuario:
- qué casos quedaron cubiertos y con qué prueba,
- resultado real de las pruebas (números, no "todo bien"),
- la **prueba real** que le toca a él, escrita siguiendo `references/prueba-real.md` (qué cuenta, qué pestaña, quién es en cada una, y las reglas que confunden: su número es dueño, ventana de 24 h, Laboratorio no es un chat),
- y pregunta si despliega: si dice que sí, usa la skill `deploy`.

Si algo de la especificación resultó imposible o mala idea al construir, dilo y pregunta; no lo cambies en silencio.
