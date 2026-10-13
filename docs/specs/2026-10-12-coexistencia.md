# Coexistencia: el negocio conecta el MISMO número de su WhatsApp Business

Fecha: 2026-10-12 · Estado: construida (falta suscribir avisos en Meta y prueba real)

## Qué y para quién
Para el dueño de un negocio chico: conecta a IaRadio el número que ya usa en la app WhatsApp Business de su celular y lo sigue usando ahí. El bot contesta por ese número; lo que el dueño escribe desde su celular aparece en el Inbox, y el bot no le contesta encima. Quita la fricción de pedir un número nuevo.

Incluye, por urgencia, pasar "Conectar con Meta" a la versión 4 del registro de Meta: la versión 2 (la que usamos) se retira el 2026-10-15 y la coexistencia va sobre la 4.

Fuente: documentación oficial de Meta (onboarding-business-app-users, implementation v4), leída el 2026-10-12.

## Decisiones del dueño
- Cuando el dueño contesta desde su celular, el bot se calla con ESE cliente 30 minutos.
- Se importan contactos e historial (hasta 6 meses, si el dueño acepta compartirlos en Meta).
- Los contactos importados NO reciben campañas hasta que le escriban al negocio.
- Se activa igual que el botón: solo admins y cuentas de prueba primero; luego todos.

## Casos (cada uno lleva su prueba)
1. "Conectar con Meta" abre el registro en la versión 4 de Meta (la 2 se retira el 15-oct). — prueba: `fbSdk.test` «caso 1» ✅
2. Si el negocio elige en Meta su número de la app WhatsApp Business, queda conectado SIN volver a registrar el número (Meta lo prohíbe en coexistencia) y la cuenta queda marcada como coexistencia. — prueba: `TestEmbeddedCoexistence::test_caso2_*` (incluye red de seguridad con `is_on_biz_app`), `TestIsOnBusinessApp`, `fbSdk.test` «caso 2» ✅
3. Al conectar en coexistencia se piden a Meta los contactos y el historial en ese momento (Meta solo da 24 h y una sola vez); si Meta falla, se avisa y la conexión no se pierde. — prueba: `test_caso3_contacts_and_history_requested_right_away`, `test_caso3_sync_failure_keeps_the_connection`, `TestInitialSyncCall` ✅
4. Si el dueño escribe a un cliente desde su celular, el mensaje aparece en el Inbox en esa plática, marcado "desde tu celular", y no cuenta como mensaje cobrado. — prueba: `test_caso4_echo_shows_in_inbox_marked_from_phone_and_is_free`, `test_caso4_same_echo_twice_is_saved_once` ✅
5. Si el dueño le escribe desde el celular a alguien que no estaba en Contactos, se crea el contacto y su plática. — prueba: `test_caso5_echo_to_unknown_number_creates_contact` ✅
6. Si un cliente escribe dentro de los 30 min después de que el dueño le contestó desde el celular, el bot NO contesta (el mensaje sí queda en el Inbox); pasados los 30 min, el bot vuelve a contestar. — prueba: `test_caso6_echo_silences_bot_for_that_customer_30_min`, `test_caso6_customer_writes_while_owner_attends_bot_does_not_answer`, `test_caso6_not_coexistence_never_checks_the_lock` ✅
7. Los contactos que llegan del celular quedan en Contactos con su nombre y como "sin consentimiento confirmado": no reciben campañas hasta que escriban. Si ya existían, no se duplican ni se les cambia nada. — prueba: `test_caso7_contacts_arrive_unconfirmed_and_existing_untouched` ✅
8. El historial importado aparece en el Inbox de cada cliente con sus fechas reales y sin duplicarse si Meta lo manda dos veces; los chats de grupo no se importan. — prueba: `test_caso8_history_lands_with_real_dates_once_and_without_groups` ✅
9. Si el dueño rechazó compartir el historial, no pasa nada malo: se registra y sigue todo normal. — prueba: `test_caso9_owner_declined_sharing_history` ✅
10. Si el negocio se desconecta desde su app (Meta avisa), la cuenta queda como desconectada en IaRadio y el bot deja de intentar enviar por ese número. — prueba: `test_caso10_business_disconnected_from_its_app`, `test_caso10_other_account_events_change_nothing` ✅
11. Antes del botón, el negocio lee qué cambia en su celular (grupos, mensajes temporales, listas de difusión, catálogo y respuestas rápidas de la app, llamadas; dispositivos vinculados se desconectan) y que puede usar su número de siempre. — prueba: `WhatsappWizard.embedded` «coexistencia caso 11» ✅
12. Los avisos de Meta de otro número o de un negocio que no existe se ignoran sin errores. — prueba: `test_caso12_events_for_unknown_numbers_are_ignored`, `test_caso12_echo_webhook_reaches_the_right_business` ✅

Pruebas: backend 1579 ✅ (`tests/test_coexistence.py` con BD y Redis reales, `tests/test_meta_whatsapp_endpoints.py`), frontend 199 ✅.

Hallazgos al construir:
- El aviso de fin de registro solo se escuchaba por `FB.Event`; la guía v4 lo manda por `window.postMessage`. Si se perdía, una coexistencia se trataba como número nuevo y se intentaba registrar (prohibido). Ahora se escuchan los dos y, además, el servidor pregunta a Meta `is_on_biz_app` antes de registrar.
- Cuando el bot estaba pausado ("escalada"), lo que escribía el cliente se guardaba como mensaje pero NO aparecía en la plática del Inbox. Corregido de paso (mismo camino que la coexistencia).
- `contacts.source` no aceptaba un valor nuevo: la migración 0073 agrega `whatsapp_app`.

## Fuera de alcance
- Que el bot "lea" los chats viejos para entrenarse (solo se muestran en el Inbox y quedan en la plática).
- Fotos, audios y archivos del historial (Meta los manda aparte; se muestran como "[archivo]").
- Grupos, llamadas, estados.
- Números comprados por IaRadio.

## Riesgos y costos
- Producción sin staging: sigue detrás del interruptor (solo admins + correos de prueba).
- Nueva columna en la base (migración): `users.meta_coexistence`.
- Lo que el dueño manda desde su celular es gratis; lo que manda el bot sigue con precios de Meta.
- El historial puede ser grande: se guarda en lotes y con tope por plática.
- Depende de que en Meta estén suscritos los avisos `history`, `smb_app_state_sync`, `smb_message_echoes` y `account_update` (lo hace el dueño en el panel de Meta).

## Plan técnico
- `frontend/src/lib/fbSdk.ts`: FB.login v4 (`extras: { setup: {} }`), manejar `FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING` (solo trae waba_id) y avisar `coexistence: true`.
- `backend/alembic/versions/0073_*`: `users.meta_coexistence` bool default false.
- `backend/app/api/v1/meta_whatsapp.py`: body `coexistence`; sin `/register` en coexistencia; pedir sync de contactos e historial (`POST /{phone_number_id}/smb_app_data` con `sync_type` `smb_app_state_sync` y `history`).
- `backend/app/services/coexistence_service.py` (nuevo): echoes → Message `sender=owner, channel=app` + plática + candado Redis 30 min; contactos; historial; account_update.
- `backend/app/api/v1/webhooks_pkg/meta_incoming.py`: despachar los 4 campos nuevos al servicio.
- `backend/app/services/inbound_pipeline.py`: si el candado del dueño está activo para ese contacto, guardar el mensaje y no contestar.
- `frontend`: Inbox muestra "Tú · desde tu celular"; asistente con los avisos de coexistencia.

## Pendientes fuera del código (dueño)
- En Meta → WhatsApp → Configuración → Webhooks: suscribir `history`, `smb_app_state_sync`, `smb_message_echoes`, `account_update`.

## Prueba real (la hace el dueño)
Con la cuenta CityCell y un número que tenga la app WhatsApp Business (versión 2.24.17+):
1. Configuración → WhatsApp → "Conectar con Meta" → en Meta elegir "conectar mi app WhatsApp Business existente" → confirmar con el código en la app.
2. La tarjeta dice "Conectado (coexistencia)"; en Contactos aparecen sus contactos; en el Inbox, sus chats.
3. Desde OTRO teléfono escribirle al negocio: el bot contesta.
4. Desde el celular del negocio, contestarle a ese cliente: aparece en el Inbox como "desde tu celular".
5. El cliente vuelve a escribir enseguida: el bot NO contesta. 30 min después: el bot sí contesta.
