# Promo dentro del chat del cliente

Fecha: 2026-10-13 · Estado: construida

## Qué y para quién
El cliente final que abre su tarjeta (/c/…) hoy solo ve las promos en "Promociones para ti"
y en el aviso de Chrome; el chat, que es la pantalla principal, las esconde. La promo debe
aparecer como burbuja dentro de la plática, con su cupón y un botón "¡La quiero!" que
hace que el bot conteste ahí mismo sabiendo de qué promo se habla.

## Decisiones del dueño
- ¿Qué promos aparecen en el chat? → Todas las que recibió (por web y por WhatsApp).
- ¿Qué hace "¡La quiero!" en la burbuja? → El bot contesta ahí mismo, con el contexto de la promo y el cupón.
- ¿A dónde lleva el aviso de Chrome de una campaña? → Al chat, con la promo ahí.

## Casos (cada uno lleva su prueba)
1. Si al cliente le llegó una promo por web (aviso de Chrome), entonces al abrir su chat la ve como burbuja del negocio, en su lugar por fecha, con su nombre ya puesto en el texto. — prueba: `test_web_promo_shows_in_chat` ✅
2. Si la promo le llegó por WhatsApp, entonces también aparece en el chat como burbuja, una sola vez. — prueba: `test_whatsapp_promo_shows_in_chat_once` ✅
3. Si la promo trae cupón vigente, entonces la burbuja muestra el código y la fecha en que vence; si ya venció o ya lo usó, la burbuja sale sin cupón. — prueba: `test_chat_promo_coupon_only_when_valid` ✅
4. Si la campaña era para otro segmento (no le llegó a este cliente), entonces no aparece en su chat. — prueba: `test_chat_never_shows_promos_not_received` ✅
5. Si el cliente toca "¡La quiero!" en la burbuja, entonces se manda "¡La quiero!" como su mensaje y el bot contesta sabiendo cuál promo y cuál cupón son. — prueba: `test_want_it_gives_bot_the_promo_context` + `test_want_it_with_foreign_or_bad_promo_gives_bot_nothing` (backend) y "¡La quiero!" sends the message with the promo (AgentChatPromo.test.tsx) ✅
6. Si el cliente llega desde la página de la promo y toca "¡La quiero!" (lo que ya existía), entonces el bot también sabe de qué promo se habla (hoy no lo sabe: error que se corrige aquí). — prueba: "coming from the promo page, the first message carries the promo (only once)" (AgentChatPromo.test.tsx) ✅
7. Si el cliente toca el aviso de Chrome de una campaña, entonces se abre el chat (no la página de la promo) con la promo hasta abajo, y la campaña cuenta como leída. — prueba: `test_campaign_web_e2e.py` (URL `?chat=1&n=` y leída en stats) + `test_web_push.py` ✅
8. Si una promo llega mientras el cliente tiene el chat abierto, entonces aparece sola en unos segundos, sin recargar. — prueba: `test_new_promo_appears_in_open_chat` ✅
9. Si el dueño ve la plática en su Inbox, entonces ve que el cliente tocó "¡La quiero!" junto con el nombre de la promo, para saber de qué le habla. — prueba: `test_inbox_sees_which_promo` ✅

## Fuera de alcance
- Campañas que no son promoción (tipos distintos de promo/lanzamiento/evento): siguen sin salir en el chat.
- Mostrar en el Inbox del dueño todas las campañas enviadas como burbujas.
- Arreglar por qué no se vio el aviso de Chrome en la prueba del 13-oct (se investiga aparte con chrome://gcm-internals).
- Audio de campañas de radio dentro de la burbuja (se sigue escuchando en la página de la promo).

## Riesgos y costos
- Nada cobrado por Meta: todo es web. No envía mensajes nuevos.
- Toca el worker (texto/URL del aviso de campaña): desplegar web + worker juntos.
- Producción sin staging: la burbuja es solo lectura; el riesgo está en no romper el historial del chat.

## Plan técnico
- `backend/app/api/v1/portal.py`: `get_messages` agrega entradas `kind="promo"` (una por campaña recibida de tipo promo, últimos 30 días) con título, texto personalizado, imagen y cupón vigente; también en el sondeo con `after`.
- `backend/app/api/v1/widget.py`: `widget_chat` acepta `promo_id`; con cliente identificado y promo que sí recibió, agrega el contexto de la promo al historial que ve el bot y deja en la plática el turno "¡La quiero! — <promo>".
- `backend/app/api/v1/portal.py` `start_chat_session`: el contexto de promo también sirve a clientes identificados (caso 6), vía el mismo `promo_id` que manda el chat.
- `backend/app/workers/task_helpers/campaign_ops.py` `_push_campaign`: el aviso abre `/c/<token>?chat=1&n=<msg>`.
- `frontend/src/components/AgentChat.tsx`: burbuja de promo (imagen, texto, cupón copiable, "¡La quiero!"); el sondeo agrega promos nuevas; "¡La quiero!" manda el mensaje con `promo_id`.

## Resultado
- Backend: 87 passed (test_promo_in_chat, test_web_conversation, test_portal, test_web_push, test_campaign_web_e2e) con Postgres y Redis locales.
- Frontend: 202 passed (37 archivos), tsc y eslint limpios.

## Prueba con la IA de verdad
- 13-oct, prueba real en prod: el bot contestó "No tengo ese dato" a "¡La quiero!" — la promo iba solo como turno de la plática y el prompt dice "responde SOLO con el contexto". Arreglo: la promo va también como `extra_note` junto al contexto del negocio (rag_service).
- Cadena real de modelos, 5 casos ("¡La quiero!" ×2, vigencia del cupón, ¿aplica a micas?, "me interesa la promo"): 5/5 — confirma 2x1 y cupón 2WTDTA3S, no inventa que aplique a micas.

## Prueba real (la hace el dueño)
1. Pestaña A: panel de CityCell → Campañas → nueva promo "Solo por web".
2. Pestaña B: la tarjeta de "Tú (prueba)" con el chat abierto → la promo aparece sola como burbuja.
3. Tocar "¡La quiero!" → el bot contesta mencionando el 2x1 / el cupón.
4. Pestaña A: Inbox → la plática muestra "¡La quiero! — <promo>".
