# El pedido se entrega al dueño (IaRadio no confirma ni cobra)

Fecha: 2026-10-21 · Estado: construida

## Qué y para quién
Hoy el bot le dice al cliente "✅ Pedido confirmado" y le manda los datos para pagar antes de que el
dueño vea el pedido: puede pagar algo que no hay o adonde no llegan. IaRadio solo toma el pedido y se
lo entrega al dueño; el pago, el tiempo y la entrega los arreglan el dueño y el cliente por WhatsApp.

## Decisiones del dueño
- ¿Hasta dónde llega IaRadio? → Toma el pedido y se lo pasa al dueño. Nada de cobrar, confirmar ni repartir.
- ¿Cómo se contactan? → El dueño, con un botón que abre SU WhatsApp con el mensaje ya escrito (sin costo de Meta).
- ¿Estados o tablas nuevas? → No.

## Casos (cada uno lleva su prueba)
1. Si el cliente termina un pedido (chat web, WhatsApp o agente), entonces el bot dice "📦 Pedido #N enviado
   a <negocio>… te escriben por WhatsApp para confirmar y acordar el pago", nunca "confirmado". — prueba: `test_caso1_caso2_caso3_web_order_is_sent_not_confirmed_and_owner_gets_the_link`,
   `TestWhatsApp::test_caso1_caso2_caso3_whatsapp_order`, `test_caso1_caso2_agent_order_is_sent_with_total_and_no_payment_data` ✅
2. Si el cliente eligió transferencia o tarjeta, entonces el bot NO le manda los datos de pago al terminar. — prueba: las mismas tres ✅
3. Si llega un pedido, entonces el aviso al dueño (WhatsApp y correo) trae un link "Escribirle al cliente" que
   abre WhatsApp con el cliente y un mensaje ya escrito: pedido, total aprox. si se sabe, "te llega / está
   listo en ___ min" y, si eligió transferencia o tarjeta, los datos de pago del negocio. En el WhatsApp va un **link corto de IaRadio**
   (`/api/v1/o/<firma>`) en la 2.ª línea del aviso, que redirige al wa.me: si el aviso sale como plantilla, Meta
   lo corta a 1,024 caracteres y el wa.me largo no cabía (hallazgo del revisor-dinero). — prueba:
   `test_caso3_cash_pickup_link_has_no_payment_data`, `test_caso3_total_in_pesos_card_link_and_no_link_without_phone`,
   `TestShortLink::*` ✅
4. Si el dueño abre un pedido en la página Pedidos, entonces ve el botón "Escribirle al cliente" con el mismo
   mensaje. — prueba: `test_caso4_list_has_the_customer_link_only_for_sent_orders` + vitest `caso4` ✅
5. Si el cliente pregunta por su pedido, entonces el agente dice que ya está con el negocio y que le escriben
   por WhatsApp; si el negocio tiene WhatsApp conectado a IaRadio da ese número, si no ofrece avisarle
   (nunca el número personal del dueño). En su portal el pedido dice "Enviado al negocio". — prueba:
   `test_caso5_asking_for_the_order_says_it_is_with_the_business` (con y sin WhatsApp conectado), `test_caso5_portal_label` ✅
6. Si el negocio importó las plantillas de ejemplo de pedido, entonces: sin cambios → se usa el texto nuevo;
   personalizadas → se respeta su texto, ahora con las variables llenas ({{order_number}}, {{items}},
   {{direccion}}, {{pago}}, {{telefono}}, {{nombre}}) y sin datos de pago; el aviso al dueño siempre lleva el
   link. También {{primer_nombre}}, {{ciudad}} y {{negocio}}. — prueba:
   `test_caso6_untouched_seed_uses_new_text_custom_one_is_filled`, `test_caso6_seeds_are_the_new_texts` ✅

Revisado en producción (solo lectura, 2026-10-21): ningún negocio tiene plantillas de pedido importadas;
todos usan el texto nuevo.

## Fuera de alcance
- Estados "por aceptar" / "esperando pago", botones Aceptar/No puedo, comprobantes de pago.
- Que el dueño conteste desde el número del negocio conectado a IaRadio (el link abre su WhatsApp normal).
- Arreglar las otras plantillas de ejemplo de pedido (pedir nombre/dirección/pago) si tienen el mismo error.

## Riesgos y costos
- Cambia lo que leen todos los clientes al pedir: solo textos; sin migración.
- Sin mensajes nuevos de Meta (el aviso al dueño ya existía; el link lo abre el dueño en su WhatsApp).
- El dueño que toca el link le escribe desde su número personal: es decisión suya, como hoy ("Responde a
  este número para contactar al cliente").
- Toca web y worker: desplegar los tres servicios juntos.

## Plan técnico
- `backend/app/services/order_handoff.py` (nuevo): texto "enviado al negocio", link wa.me con mensaje
  prellenado, total aprox. desde OrderItem, llenado de variables de plantillas y detección de semilla sin cambios.
- `widget_order_service.py`, `inbound_pipeline.py`, `customer_agent.py` (`_do_order`, `mis_pedidos`, prompt): usan lo anterior.
- `core/email.py`: botón "Escribirle al cliente".
- `api/v1/template_seeds.py`: textos nuevos de las dos semillas.
- `api/v1/orders.py`: `customer_wa_link` en la lista; `api/v1/portal.py`: etiqueta "Enviado al negocio".
- `frontend/src/pages/OrdersPage.tsx`: botón.
- `api/v1/orders.py` `public_router` + `main.py`: `GET /api/v1/o/{token}` (firma HMAC, como el portal) → 302 al wa.me.

## Prueba real (la hace el dueño)
Antes: en Pedidos, los datos de pago (CLABE) llenos; en Configuración, "Entrego a domicilio" encendido;
al menos un producto con precio en el catálogo.
1. "Probar como cliente": **"quiero 2 <producto de tu catálogo> pa' mi casa, pago por transferencia"** y termina el pedido →
   el bot dice "📦 Pedido #N enviado a <tu negocio>… te escriben por WhatsApp". No dice "confirmado" ni
   manda la CLABE.
2. En el mismo chat: **"¿ya está mi pedido?"** → dice que ya está con el negocio y que te escriben; no da
   tu número personal.
3. En tu WhatsApp llega el aviso del pedido con "👉 Escribirle al cliente" en la 2.ª línea. Tócalo → abre
   WhatsApp con el cliente y un mensaje ya escrito: el pedido, el total aprox., "te llega en ___ min" y tu CLABE.
   No lo mandes si el número es de prueba.
4. Página Pedidos: el pedido tiene el botón "Escribirle al cliente" con el mismo mensaje.
5. Portal del cliente (`/mi`): el pedido dice "Enviado al negocio".
