# El bot aprende de lo que el dueño contesta en el Inbox

Fecha: 2026-10-12 · Estado: construida

## Qué y para quién
Para el dueño del negocio: cuando contesta a un cliente desde el Inbox algo que sirve para todos (precio, horario, envíos, políticas), se le ofrece guardarlo para que el bot lo sepa la próxima vez. Así el bot se completa solo con el trabajo que el dueño ya hace, sin capturar nada aparte.

## Decisiones del dueño
- ¿Cuándo preguntar? → Solo si la respuesta sirve como información del negocio (lo decide la IA); si es personal, no se pregunta nada.
- ¿Qué se guarda? → Versión general (pregunta + respuesta, sin nombre ni datos del cliente), que el dueño puede corregir antes de guardar.
- ¿Si contradice algo que el bot ya sabía? → Reemplazar lo viejo, mostrándole antes qué decía el bot.
- ¿Para quién? → Todos los negocios desde el inicio.

## Casos (cada uno lleva su prueba)
1. Si el dueño contesta desde el Inbox algo del negocio ("sí hacemos envíos, $30 a todo Tlaxiaco"), entonces debajo de su mensaje aparece la tarjeta "¿Guardo esto para que el bot lo sepa?" con la pregunta y la respuesta redactadas en general. — prueba: `test_caso1_business_info_gets_a_suggestion`, `test_caso1_ai_sees_the_customer_question_and_owner_reply`, LearnCard «caso 1» ✅
2. Si lo que contesta es personal o de ese momento ("ya va tu pedido", "te espero a las 5", "gracias"), entonces no aparece ninguna tarjeta. — prueba: `test_caso2_personal_reply_gets_no_suggestion`, LearnCard «caso 2 y 8» ✅
3. La versión redactada no lleva el nombre, teléfono ni datos del cliente. — prueba: `test_caso3_suggestion_with_customer_name_or_phone_is_dropped`, `test_caso3_placeholder_contact_name_does_not_block` ✅
4. Si el dueño corrige el texto y toca Guardar, entonces se guarda exactamente lo que dejó escrito, aparece en la Base de conocimiento como "respuestas-del-dueño" y el bot lo encuentra cuando otro cliente pregunta algo parecido. — prueba: `test_caso4_saves_the_edited_text_and_the_bot_finds_it`, LearnCard «caso 4» ✅
5. Si el dueño toca "No", entonces no se guarda nada y la tarjeta desaparece. — prueba: `test_caso5_saying_no_saves_nothing`, LearnCard «caso 5» ✅
6. Si antes el dueño ya había guardado una respuesta distinta sobre lo mismo (envío $25 → ahora $30), entonces la tarjeta le muestra "Antes el bot decía: …" y al guardar la vieja se desactiva (el bot deja de usarla). — prueba: `test_caso6_contradicted_owner_answer_is_shown_and_replaced`, `test_caso6_same_topic_without_contradiction_replaces_nothing`, LearnCard «caso 6» ✅
7. Si lo que contradice está dentro de un documento que el dueño subió (PDF, menú), entonces la tarjeta le avisa "Tu documento «menu.pdf» dice otra cosa — corrígelo ahí"; la respuesta nueva sí se guarda, pero el documento no se toca (desactivarlo borraría también todo lo demás que dice). — prueba: `test_caso7_contradicted_document_is_warned_not_touched`, LearnCard «caso 7» ✅
8. Si la IA falla o tarda, entonces el mensaje del dueño se envía igual y simplemente no sale la tarjeta: aprender nunca frena una respuesta al cliente. — prueba: `test_caso8_ai_failure_means_no_card`, `test_caso8_conflict_check_failure_still_suggests`, LearnCard «caso 8» ✅
9. Un negocio no puede ver sugerencias de conversaciones de otro ni desactivar conocimiento de otro. — prueba: `test_caso9_other_business_cannot_suggest_or_replace`, `test_caso9_only_owner_messages_can_be_learned` ✅

Pruebas: backend `tests/test_inbox_learning.py` (BD real), frontend `src/__tests__/LearnCard.test.tsx`.
Con la IA real (2026-10-12): 7 de 7 respuestas bien clasificadas (4 útiles, 3 personales), sin nombre del cliente en lo redactado, y la contradicción $25 → $30 detectada.

## Fuera de alcance
- Lo que el dueño contesta desde la app de WhatsApp de su teléfono (eso depende de la coexistencia, que aún no existe).
- "Déjame preguntarle al dueño" por WhatsApp: ya aprende solo, no se cambia.
- Lista de preguntas que el bot no supo contestar, memoria por cliente, cambiar las instrucciones del bot.
- Editar o corregir documentos subidos (solo se avisa).

## Riesgos y costos
- Una o dos llamadas de IA por cada respuesta del dueño en el Inbox (cadena gratis primero; bajo costo). No se manda ningún WhatsApp extra.
- Nada se guarda sin que el dueño toque Guardar.
- Sin cambios en workers de Celery ni migraciones.

## Plan técnico
- `backend/app/services/inbox_learning.py` (nuevo): `suggest(db, advertiser, conv, msg_id)` toma las preguntas del cliente justo antes de la respuesta del dueño, una llamada de IA decide si sirve y la redacta en general (JSON), busca en la base de conocimiento lo parecido (pgvector, como `rag_service.search_knowledge`) y una segunda llamada marca qué contradice. `save(...)` reusa `owner_question_service._learn` y desactiva solo los "respuestas-del-dueño" contradichos del mismo negocio.
- `backend/app/api/v1/conversations.py`: `POST /conversations/{id}/learn-suggestion` (con `msg_id`) y `POST /conversations/{id}/learn` (pregunta, respuesta, ids a reemplazar). La respuesta al cliente (`/reply`) no cambia: la sugerencia se pide después de enviarla.
- `frontend/src/pages/InboxPage.tsx` + componente `LearnCard`: tras enviar, pide la sugerencia; si hay, muestra la tarjeta editable con Guardar / No y los avisos de "antes decía".

## Prueba real (la hace el dueño)
1. En el Inbox, contesta a un cliente algo del negocio (ej. "Sí, hacemos envíos, $30").
2. Debe salir la tarjeta con la pregunta y respuesta en general; corrige algo y toca Guardar.
3. Desde otro teléfono pregúntale al bot "¿hacen envíos?" y debe contestar con lo que guardaste.
4. Contesta algo personal ("ya va tu pedido") y no debe salir tarjeta.
