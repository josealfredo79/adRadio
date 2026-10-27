# Avisos de pedido y cita al dueño por el número central

Fecha: 2026-10-23 · Estado: aprobada

## Qué y para quién
Para el dueño del negocio. Hoy el aviso de un pedido o una cita nueva le llega solo por el WhatsApp
propio del negocio o por correo. Un dueño que se dio de alta por WhatsApp no tiene correo real y casi
ninguno tiene su número conectado a Meta al principio: el cliente pide, el bot le dice "te escriben por
WhatsApp" y el dueño nunca se entera. Con este cambio el aviso le llega desde el número central de
IaRadio (el mismo que ya le manda las preguntas que el bot no sabe contestar).

## Decisiones del dueño
- ¿Por dónde? → Opción A: número central de IaRadio (texto libre si el dueño escribió en 24 h; si no,
  la plantilla utility `aviso_dueno`, ~US$0.0085 por aviso).
- Tope por negocio al día → 30 avisos por el número central.
- Al llegar al tope → un último aviso ("los demás están en tu panel") y nada más hasta el día siguiente.
- Negocio con WhatsApp propio al que Meta le rechaza el aviso (fuera de 24 h) → se manda por el central,
  dentro del mismo tope.

## Casos (cada uno lleva su prueba)
1. Si un negocio sin WhatsApp propio recibe un pedido (chat web o agente), entonces al dueño le llega el
   aviso por el número central con el botón "👉 Escribirle al cliente". — prueba:
   `test_caso1_order_notice_goes_through_central_without_own_whatsapp`
2. Si un negocio sin WhatsApp propio recibe una cita, entonces al dueño le llega el aviso por el número
   central. — prueba: `test_caso2_appointment_notice_goes_through_central`
3. Si el negocio tiene su WhatsApp conectado y Meta acepta el aviso, entonces sale por su número y el
   central no se usa ni cuenta para el tope. — prueba: `test_caso3_own_whatsapp_first`
4. Si el negocio tiene su WhatsApp conectado y Meta lo rechaza, entonces el aviso sale por el central.
   — prueba: `test_caso4_own_rejected_falls_back_to_central`
5. Si el negocio ya mandó 30 avisos por el central hoy (hora de México), entonces el aviso 31 es uno solo
   que dice que los demás están en su panel, del 32 en adelante no sale nada, y al día siguiente vuelve a
   avisar normal. — prueba: `test_caso5_daily_cap_then_one_last_notice`
6. Si el dueño no tiene celular registrado (o el número central no está configurado), entonces no se
   manda nada y el pedido o la cita se guardan igual. — prueba: `test_caso6_no_owner_phone_sends_nothing`
7. El correo de aviso sigue saliendo igual que hoy. — prueba: `test_caso7_email_still_sent`

## Fuera de alcance
- Notificaciones del navegador (push) para el dueño (opción B, después).
- Pedir correo en el alta (opción C).
- Los avisos de cancelación o cambio de cita del agente: ya salen por el central, se quedan igual.
- El flujo viejo de pedidos por WhatsApp (`inbound_pipeline`): ya usa el central para el dueño.

## Riesgos y costos
- Mensajes que Meta cobra: plantilla utility ~US$0.0085 (≈16 centavos) solo fuera de la ventana de 24 h.
  Peor caso con el tope: 31 avisos/día por negocio ≈ $5 pesos/día. Lo paga IaRadio, no cuenta en la
  cuota del plan del negocio.
- **Corrección 2026-10-26 (prueba real, pedido #0003):** Meta acepta el texto libre fuera de la
  ventana y lo tumba después por webhook (131047), así que el respaldo con plantilla nunca corría;
  ahora se decide antes de mandar, con la ventana anotada en Redis cuando el dueño le escribe al
  central. Y `aviso_dueno` no existía: pedidos y citas usan `aviso_negocio_dueno` y `cita_nueva_dueno`
  (Utilidad), ver docs/NUMERO_CENTRAL_IARADIO.md.
- (Original) La plantilla `aviso_dueno` (es_MX) es la misma que ya usan las preguntas al dueño; no hay que aprobar
  plantillas nuevas. Si no estuviera aprobada en Meta, el aviso falla igual que hoy (se ve en los
  registros como "Template to … failed").
- Si el dueño contesta el aviso en el central, su mensaje lo toma el Copiloto (como hoy con cualquier
  mensaje suyo que no contesta una pregunta).
- Si Redis no responde, el aviso se manda igual (sin contar): perder un pedido cuesta más que un aviso.
- Toca web y worker: desplegar los dos (Railway lo hace junto con un push a master).

## Plan técnico
- `backend/app/services/owner_notify.py` (nuevo): `notify_owner(advertiser, body)` — WhatsApp propio
  primero; si no hay o falla, número central con tope diario en Redis (`owner_notify:{id}:{AAAA-MM-DD}`,
  hora de México, vence en 2 días).
- `backend/app/services/widget_order_service.py` y `appointment_booking_service.py`: su `_notify_owner`
  usa `notify_owner` en vez de `send_whatsapp` directo.
- `backend/tests/test_owner_notify.py` (nuevo): casos 1–7.

## Prueba real (la hace el dueño)
1. Cuenta CityCell (sin WhatsApp conectado). Revisa que en Configuración → Teléfono esté tu celular.
2. Pestaña nueva → Configuración → Agente inteligente → "Probar como cliente" → pide un cargador para
   recoger y confirma.
3. En tu celular, en el chat con el número de IaRadio, debe llegar "📦 NUEVO PEDIDO #000N" con el botón
   "👉 Escribirle al cliente". Tócalo: abre WhatsApp con el mensaje listo para el cliente.
4. Ojo: tu celular es el del dueño; el "cliente" de la prueba eres tú mismo desde la web.
