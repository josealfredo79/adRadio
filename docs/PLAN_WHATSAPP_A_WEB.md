# Plan: de WhatsApp a la web

**Idea central:** WhatsApp es la puerta, la web es la casa. WhatsApp sirve para el primer contacto y los avisos importantes; todo lo demás (ver citas, pedidos, promos, seguir platicando) pasa en la web del negocio, que es gratis, más rica y nuestra.

**Por qué ahora:** desde el 1-oct-2026 Meta cobra también los mensajes de servicio (las respuestas del bot dentro de la ventana de 24 h), no solo las plantillas. Cada ida y vuelta por WhatsApp le cuesta al negocio; cada visita a la web no. Fuente oficial: https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/non-template-messages

**Lo que cambia en lo que vendemos:** de "un bot de WhatsApp" (hay cientos) a "tu negocio con app propia para tus clientes: citas, pedidos, cupones y promos — y te ahorra mensajes de Meta".

---

## Fase 1 — Portal del cliente ✅ (construido 2026-10-01)

Un link personal `/c/{token}` que el bot agrega al final de cada confirmación de cita o pedido. El cliente lo abre sin contraseña y ve:

- Sus **próximas citas**, con botón para **cancelar** (Google Calendar se actualiza y el dueño recibe aviso por el número central si está configurado).
- Sus **cupones vigentes**, con botón para copiar el código.
- Sus **pedidos** y su estado ("Sin terminar" si lo abandonó).
- **Promociones para ti**: solo las campañas que ese cliente sí recibió.
- **Chat con el bot dentro de la página** — gratis, ya ligado al cliente (puede pedir o agendar sin volver a dar nombre y teléfono).

**Promos (opción A + B del análisis):**
- El texto de cada campaña (pie del banner, o el texto que ya acompaña a la nota de voz) lleva el link a la promo completa. **No cuesta un mensaje extra**: va en el mismo mensaje.
- La página de la promo muestra imagen, texto personalizado, el cupón del cliente y "¡La quiero!", que abre el chat **con el contexto de la promo y del cupón ya cargado** para el bot.

**Dashboard:** botón "Copiar link del portal" en cada contacto.

**Seguridad:** el token es el id del contacto + firma HMAC con `SECRET_KEY` (no se guarda en BD). Un link nunca ve ni toca datos de otro contacto (cubierto por tests). Rotar `SECRET_KEY` invalida todos los links; el bot manda uno nuevo en la siguiente confirmación.

**Bug encontrado y corregido en el camino:** un pedido a medias abandonado (de días antes) se "comía" el siguiente mensaje del cliente — por WhatsApp y por el widget. Ahora solo se retoma si se empezó en las últimas 2 horas (`ORDER_RESUME_WINDOW`).

**Archivos:**
- Backend: `app/services/portal_service.py`, `app/api/v1/portal.py`, `GET /contacts/{id}/portal-link`, link en confirmaciones (`appointment_booking_service.py`, `widget_order_service.py`, `inbound_pipeline.py`) y en campañas (`campaign_ops.py`).
- Frontend: `src/pages/PortalPage.tsx` (rutas `/c/:token` y `/c/:token/promo/:promoId`), botón en `ContactsPage.tsx`.
- Tests: `tests/test_portal.py`, `tests/test_widget_order_service.py::TestStalePendingOrder`.

**Qué medir (siguientes 4 semanas):**
- % de clientes que abren el link (visitas a `/c/...` vs. links enviados).
- Mensajes de WhatsApp por cliente antes y después.
- Cancelaciones hechas desde el portal (antes eran conversaciones de 3–5 mensajes).
- Clics en "¡La quiero!" y cupones canjeados que vinieron de una promo.

---

## Fase 2 — Notificaciones web ✅ (construido 2026-10-01)

Avisos que llegan a la pantalla del celular **gratis**, para los clientes que los aceptan en su portal.

- Tarjeta en el portal: *"¿Te aviso un día antes de tu cita?"* (o *"…de promociones y cupones?"* si no tiene cita). Un toque y listo.
- **Android**: funciona directo desde el navegador. **iPhone**: la tarjeta explica cómo "Agregar a inicio"; el portal se instala como la app del negocio (manifest propio con su nombre y color) y desde ahí se activan.
- **Recordatorios de cita** (24 h y 1 h): si el cliente tiene avisos activos, van por notificación y no por WhatsApp. La notificación lleva al portal, donde ahora también hay **"Confirmar asistencia"** (el "responde 1" de WhatsApp).
- **Campañas**: el ruteo es automático por cliente — notificación si la activó, WhatsApp si no. Por notificación no se manda plantilla, no se descuenta del saldo del plan, y no se genera audio ni banner. Si el negocio se queda sin saldo de WhatsApp, los clientes con notificaciones siguen recibiendo la campaña.
- Si la notificación falla (navegador dado de baja, servicio caído), se cae a WhatsApp como antes. Las suscripciones muertas (404/410) se borran solas.
- **Estadísticas**: cada envío por notificación cuenta como "enviado"; cuando el cliente la toca pasa a "leído".

**Bug encontrado y corregido:** los recordatorios de WhatsApp mostraban la hora en UTC (6 h adelantada) y el día en inglés.

**Configuración:** `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` en Railway (adRadio y worker). Generar con `python -m app.services.web_push --generate`. Sin llaves, todo queda apagado y sigue saliendo por WhatsApp. **No rotar las llaves sin necesidad**: cambiarlas invalida todas las suscripciones existentes.

**Archivos:** `app/models/push_subscription.py` (migración 0061), `app/services/web_push.py`, endpoints en `app/api/v1/portal.py`, ruteo en `campaign_ops.py` y `appointment_ops.py`, `frontend/public/portal-sw.js`, tarjeta en `PortalPage.tsx`. Tests: `tests/test_web_push.py`.

**Probado de punta a punta** con Chromium real: activar avisos → se guarda la suscripción → el backend manda la notificación por el servicio de push de Google → el navegador la recibe.

**Qué medir:** % de clientes del portal que activan avisos; recordatorios y campañas enviados por notificación vs. WhatsApp (ahorro directo); tasa de "leído" de las notificaciones.

**Siguiente mejora posible:** mostrarle al dueño en el dashboard cuántos clientes tienen avisos activos y cuánto se ahorró.

---

## Fase 3 — Tarjeta en la cartera del celular (solo si hay demanda)

Tarjeta de lealtad (sellos, puntos, cupón) en Google Wallet / Apple Wallet que se actualiza sola y avisa en la pantalla de bloqueo.

- Empezar por **Google Wallet** (la mayoría de los clientes en México usan Android).
- Apple requiere cuenta de desarrollador ($99 USD/año), certificados de firma y un servicio web para actualizar pases.
- **Estimado:** 3–4 semanas. Hacerlo cuando algún negocio pida tarjeta de lealtad.

---

## Descartado

- **Correo:** pocos clientes de pymes mexicanas dejan correo; bajo alcance.

## Pendientes conocidos (fuera de este cambio)

- Si un negocio no tiene base de conocimiento ni instrucciones, el bot responde un saludo fijo que ignora la conversación (`rag_service.py`, "Pure fallback") e inserta `bot_personality` tal cual en la frase. Conviene pedir instrucciones mínimas en el onboarding.
- El aviso de cookies tapa el botón flotante del chat hasta que se acepta (es global del sitio).
