# ¿Para cuál negocio? (número central con varias cuentas)

Fecha: 2026-10-29 · Estado: construida

## Qué y para quién
Un dueño cuyo celular está en más de una cuenta de IaRadio (hoy: el dueño con IaRadio y CityCell)
le escribe al número central. El Copiloto por WhatsApp usaba siempre "la primera" cuenta que
encontraba: la campaña "2x1 en micas" del 29-oct (14:28, campaña 6d3258d9) salió desde IaRadio
en vez de CityCell. Ahora pregunta con botones para cuál negocio es.

## Decisiones del dueño
- Opción A: preguntar con botones "¿Para cuál negocio?" (no "nunca usar la cuenta IaRadio").
- Recordar el negocio escogido hasta 12 h sin escribir; "cambiar negocio" vuelve a preguntar.
- El nombre del negocio se dice al escoger y antes de mandar una campaña, no en cada respuesta.

## Casos (cada uno lleva su prueba)
1. Si mi celular está en dos cuentas y le escribo al central sin haber escogido, entonces me
   contesta "¿Para cuál negocio?" con un botón por negocio y todavía no hace nada. — prueba: `test_two_accounts_ask_which_business_before_doing_anything` ✅
2. Si toco "CityCell", entonces me dice "Listo, ahora estás en CityCell 🏪" y atiende lo que
   había pedido (p. ej. armar la campaña) en CityCell, sin que lo repita. — prueba: `test_tapping_a_business_confirms_and_does_what_was_asked_there` ✅
3. Si sigo escribiendo antes de 12 h, no vuelve a preguntar y todo va a CityCell (cada mensaje
   renueva las 12 h). — prueba: `test_choice_is_remembered_and_each_message_renews_the_12_hours` ✅
4. Si pasan 12 h sin escribir, la siguiente vez vuelve a preguntar. — prueba: `test_after_12_hours_without_writing_it_asks_again` ✅
5. Si escribo "cambiar negocio", me vuelve a preguntar. — prueba: `test_change_business_asks_again_and_the_new_choice_sticks` ✅
6. Si tengo varias cuentas, antes de mandar una campaña (armador o promo rápida del Copiloto) el
   mensaje dice "Se manda a los clientes de CityCell". — prueba: `test_before_sending_a_campaign_it_says_which_business`, `test_quick_promo_confirmation_says_which_business` ✅
7. Si tengo más de 3 negocios, sale una lista en vez de botones. — prueba: `test_more_than_three_businesses_get_a_list` ✅
8. Si mientras pregunta escribo otra cosa que no es un negocio, me vuelve a mostrar los botones y
   no pierde lo que había pedido primero. — prueba: `test_typing_something_else_shows_the_buttons_again_and_keeps_the_first_request` ✅
9. Si mando una foto sin haber escogido, pregunta el negocio y, al escoger, me pide que la mande
   otra vez. — prueba: `test_photo_before_choosing_asks_and_then_asks_for_the_photo_again` ✅
10. Si contesto la pregunta de un cliente (citando el aviso o con la única pregunta pendiente),
    se contesta sin preguntar el negocio, como hoy. — prueba: `test_answer_to_a_customer_never_asks_for_the_business`, `test_unquoted_answer_to_the_only_pending_question_never_asks_for_the_business` ✅
11. Si mi celular está en una sola cuenta, todo sigue igual: nunca pregunta ni dice el nombre. — prueba: `test_one_account_never_asks` ✅

## Fuera de alcance
- Los avisos al dueño (pedidos, citas, cancelaciones): ya dicen de qué negocio son.
- Escoger negocio en el panel web (ahí cada cuenta tiene su propio inicio de sesión).
- Guardar la foto mientras pregunta (se pide otra vez; pasa poco).

## Riesgos y costos
- Los botones van como respuesta a un mensaje que el dueño acaba de mandar: dentro de la ventana
  de 24 h, Meta no los cobra.
- Sin Redis no hay dónde recordar la elección: se usa la primera cuenta como hoy (y queda en logs).
- Toca solo la web (webhook del central); worker y beat no cambian.

## Plan técnico
- `backend/app/services/central_account_picker.py` (nuevo): elección en Redis
  `central_owner:<número>` (TTL 12 h que se renueva) y lo pedido mientras pregunta en
  `central_pick:<número>`; botones (≤3) o lista; "cambiar negocio".
- `backend/app/services/owner_question_service.py` (`handle_owner_message`): con varias cuentas,
  primero las respuestas a clientes; luego el selector decide la cuenta en vez de `owners[0]`.
- `backend/app/services/copilot_whatsapp_service.py`: `handle_owner_command(..., business=)`; el
  paso "send" del armador y la confirmación de promo llevan "Se manda a los clientes de X".
- `backend/app/api/v1/webhooks_pkg/meta_incoming.py`: el toque de un botón `pick:` llega con su id.
- `backend/tests/test_central_account_picker.py`: una prueba por caso.

## Prueba real (la hace el dueño)
1. Con tu celular (está en IaRadio y CityCell), escríbele al número central: "haz una campaña de
   2x1 en micas este viernes".
2. Debe contestar "¿Para cuál negocio?" con botones IaRadio y CityCell. Toca **CityCell**.
3. Debe decir "Listo, ahora estás en CityCell 🏪" y seguir con la campaña. Elige **Texto** →
   **Uno** → 9531953182. Antes de mandarla debe decir "Se manda a los clientes de CityCell".
4. En Chrome, `/mi` (9531953182): la promo aparece en el chat de **CityCell**, no en IaRadio.
5. Escribe "cambiar negocio": debe volver a preguntar.

## Resultado (2026-10-29)
- Backend: suite completa en local (`scripts/test_local.sh`) sin fallas, 1 saltada (la de caplog solo
  falla con `-p no:logging`; sola pasa). 20 pruebas en `tests/test_central_account_picker.py`
  (base y Redis reales; WhatsApp y Copiloto falsos).
- revisor-dinero: "No subir" por un hueco, arreglado con prueba:
  - Sin negocio escogido, un botón viejo del armador ("Mandar gratis por web") podía tomarse como
    respuesta a un cliente → ahora se revisa el armador de todas las cuentas y se pregunta el
    negocio; al escoger se vuelve a mostrar el paso, nada sale solo
    (`test_old_campaign_button_without_a_business_never_reaches_a_customer_nor_sends`).
  - Nombres parecidos que WhatsApp recorta igual → el botón viaja con su id `pick:<cuenta>`
    (`test_names_that_look_the_same_on_a_button_pick_by_id`,
    `test_webhook_passes_the_pick_id_instead_of_the_cut_title`).
  - Cuentas en orden de alta y "1"/"2" solo cuentan mientras se pregunta
    (`test_a_number_only_picks_while_being_asked`).
- Re-revisión: "Subir". Sus dos detalles menores también arreglados: un botón viejo de "¿Para cuál
  negocio?" cambia de cuenta aunque ya haya una (`test_old_pick_button_switches_business_even_with_one_already_chosen`)
  y un "Sí" de antes de escoger nunca se aplica solo (`test_a_yes_before_choosing_is_never_applied_on_its_own`).
- Sin cambios de prompts (no aplica probar_ia). Sin migración.
