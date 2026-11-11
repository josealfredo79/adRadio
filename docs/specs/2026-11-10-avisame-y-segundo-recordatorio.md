# "🔔 Avísame" en el chat web y segundo recordatorio

Fecha: 2026-11-10 · Estado: construida

## Qué y para quién
El seguimiento automático (spec 2026-10-15) casi nunca le llega a quien platicó por la web: solo
sale por aviso web si el cliente activó los avisos, y casi nadie llega a su espacio `/mi` a
activarlos. Además solo hay un recordatorio (~20 h). Esto le ofrece los avisos al cliente justo
cuando pregunta por un producto, con un toque, y agrega un segundo recordatorio gratis a los 3 días.

## Decisiones del dueño
- ¿A quién le sale el botón? → A identificados y a anónimos (el anónimo se registra con su
  WhatsApp y código, el mismo registro que ya existe en el chat).
- ¿Cuándo el segundo recordatorio? → A los 3 días.
- ¿Qué dice? → La IA, sobre lo que preguntó; si falla, texto fijo.
- ¿Cómo se enciende? → Para todos (respeta el interruptor de seguimiento de cada dueño).

## Casos (cada uno lleva su prueba)
1. Si un cliente identificado (llegó por su link o se registró en el chat) pregunta por un producto
   y el bot le muestra la tarjeta del producto, entonces debajo sale "🔔 ¿Te aviso por aquí de esto
   y de las promos?" con "Sí, avísame" / "Ahora no". — prueba: `offers_notify_after_product_card` ✅
2. Si toca "Sí, avísame" y el celular acepta, entonces quedan activados los avisos (los mismos del
   portal) y ve "🔔 Listo, te aviso al celular". — prueba: `offers_notify_after_product_card` ✅
3. Si un visitante anónimo de `/sitio` ve la tarjeta de un producto, entonces sale "🔔 Avísame";
   al tocarlo pide nombre y WhatsApp, le manda el código y, verificado, le ofrece activar los
   avisos. — prueba: `anonymous_avisame_opens_join_then_offers_notify` ✅
4. Si el cliente ya tiene los avisos activados, o su celular no los soporta (iPhone sin instalar
   la página, navegador sin avisos), entonces no sale nada. — prueba: `no_offer_when_on_or_unsupported` ✅
5. Si ya tocó "Ahora no" o ya salió la oferta en esta plática, entonces no se le vuelve a ofrecer
   con cada producto. — prueba: `offer_shows_once_per_chat` ✅
6. Si un cliente con avisos activados recibió el primer recordatorio, no compró, no agendó ni
   volvió a escribir, y pasaron 3 días desde su último mensaje, entonces le llega un segundo
   recordatorio por aviso web sobre lo que preguntó. — prueba: `second_followup_after_3_days` ✅
7. Si el cliente volvió a escribir después del primer recordatorio, o ya pidió/agendó/canjeó,
   entonces no hay segundo recordatorio. — prueba: `no_second_when_replied_or_converted` ✅
8. El segundo recordatorio sale UNA vez por plática, nunca de 9 pm a 9 am, nunca si el dueño
   apagó el seguimiento o tiene la pausa puesta, y si ya pasaron más de 4 días ya no sale.
   — prueba: `second_followup_only_once_and_in_window` ✅
9. El segundo recordatorio NUNCA sale por WhatsApp: sin avisos web activados, no se le escribe
   (ni se vuelve a anotar en el resumen del dueño). — prueba: `second_followup_never_whatsapp` ✅
10. Si la IA falla o el texto sale cortado, el segundo recordatorio usa un texto fijo y no inventa
    precios, descuentos ni existencias. — prueba: `second_followup_fallback_and_no_invented_stock` ✅
11. El primer recordatorio (20 h) sigue exactamente como hoy. — prueba: suite actual de
    `tests/test_followup.py` sin cambios ✅ (35/35 junto con las nuevas).

## Fuera de alcance
- Segundo recordatorio por WhatsApp (requiere plantilla de marketing de Meta, cobrada).
- Más de dos recordatorios por plática.
- Pedir avisos en el chat de ventas de IaRadio (landing): no tiene registro de cliente.
- Botón para que el dueño cambie los 3 días.

## Riesgos y costos
- El registro del anónimo manda un código por WhatsApp (el mismo de `/q/` y `/mi`, ya con topes
  anti-bots): costo de un mensaje de autenticación de Meta (~$0.0085 USD) por registro.
- Los avisos web no cuestan.
- El segundo recordatorio corre en el worker (Celery beat cada 15 min): desplegar web + worker.
- Sin cambios a la base de datos.

## Plan técnico
- `frontend/src/components/ChatNotifyOffer.tsx`: prop `reason: 'appointment' | 'product'` con su
  texto; el de cita queda igual.
- `frontend/src/components/AgentChat.tsx`: tras la última respuesta con tarjeta de producto (de
  esta plática), si hay token → `ChatNotifyOffer reason="product"`; si no hay token y el negocio
  tiene registro (`/q/slug`) → botón "🔔 Avísame" que abre `InlineJoin`; al verificar, la oferta.
  Una vez por plática.
- `backend/app/services/followup_service.py`: `run_second_followups` (llamada desde
  `run_followups`): elegible si tiene avisos, su último recordatorio fue después de su último
  mensaje y antes de 3 días de él, pasaron entre 3 y 4 días desde su último mensaje y ≥24 h desde
  el primer recordatorio, sin conversión. Marca `last_followup_at` (así no se repite).
  `write_message(..., second=True)` con su propio texto para la IA.

## Prueba real (la hace el dueño)
1. En un celular Android (Chrome), abre `iaradio.online/sitio/citycell` sin haber entrado antes
   (pestaña de incógnito no sirve: no deja avisos). Pregunta "¿cuánto cuesta el cargador?".
2. Debajo de la tarjeta del cargador toca "🔔 Avísame", pon tu nombre y un WhatsApp que NO sea el
   del dueño (9531953182 es dueño), escribe el código y toca "Sí, avísame". Acepta el permiso.
3. A las ~20 h (de 9 am a 9 pm) debe llegarte al celular el primer recordatorio. No compres.
4. A los 3 días, el segundo. En el Inbox de CityCell se ven los dos como mensajes "web".

## Resultados (2026-11-10)
- Backend: 2,178 pruebas pasan (suite completa); `tests/test_second_followup.py` (casos 6-10) y `tests/test_followup.py` (caso 11): 35/35.
- Frontend: 278/278 (`src/__tests__/AgentChatAvisame.test.tsx`, casos 1-5: 10/10); tsc y eslint limpios.
- IA real (Gemini 3.5 flash-lite) con el texto del segundo recordatorio: 5/5 sin "disponible", descuentos ni datos
  personales. Ajuste: "ni que ya tienes una respuesta que no está en la plática" (salía "¿pude conseguirte el dato…").

## Prueba e2e en local con navegador real (2026-11-10)
Chromium real + backend real + Postgres/Redis desechables; envío web push real (cifrado VAPID)
hacia un receptor local que lo descifra; reloj adelantado para los recordatorios. Resultado ✅:
pregunta → tarjeta → "🔔 Avísame" → nombre/WhatsApp → código → "Sí, avísame" → "Listo";
primer aviso a las ~20 h y segundo a los 3 días llegaron descifrados; 15 min después, 0.

Encontró y se arregló:
- **El registro con código no pasaba la plática anónima** a la cuenta: el cliente activaba avisos
  y el seguimiento nunca tenía qué recordarle. Ahora `/public/join/{slug}/verify` recibe
  `session_id` y `adopt_anonymous_chat` la pasa (prueba `tests/test_join_adopts_chat.py`).
- **"Sí, avísame" se quedaba girando en `/sitio`** (también el de la cita, que ya estaba en
  producción): `navigator.serviceWorker.ready` no se resuelve fuera de `/c/`. Ahora se espera al
  registro (`untilActive`, prueba `webPushUntilActive.test.ts`).
- El cuadro "Avísame" quedaba fuera de la vista: ahora el chat baja para mostrarlo.

Resultados finales: backend 2,182 ✅, frontend 281 ✅.
