# Botones al mostrar un producto en WhatsApp

Fecha: 2026-11-09 · Estado: construida

## Qué y para quién
Cuando el bot le muestra un producto al cliente final por WhatsApp, hoy le pregunta "¿Te gustaría hacer
el pedido?" pero no le da nada que tocar: tiene que escribir, y "lo quiero" ni siquiera arranca un pedido.
Con esto el cliente toca **🛒 Lo quiero** y termina su pedido tocando botones (nombre, entrega, pago).
Detectado en la prueba real de CityCell del 2026-11-09 (bocinas $350).

## Decisiones del dueño
- ¿Qué botones? → **🛒 Lo quiero** + **❓ Otra pregunta** (apartar = pedido para recoger, no aparte).
- ¿Qué pasa al tocar "Lo quiero"? → **Pedido completo con botones**, sin volver a preguntar "¿quieres pedir?".
- ¿Cómo se ve el producto? → **Foto del producto arriba** en el mismo mensaje si la tiene; el link sigue en el texto.
- ¿Para quién? → **Para todos los negocios** desde que se sube (sin bandera); si algo falla, sale el texto de hoy.

## Casos (cada uno lleva su prueba)
1. Si el bot contesta sobre UN producto del catálogo por el número propio del negocio, entonces la respuesta
   sale en un solo mensaje con los botones **🛒 Lo quiero** y **❓ Otra pregunta**, y el texto conserva el link
   del producto. — prueba: `test_caso1_producto_sale_con_lo_quiero_y_otra_pregunta_y_conserva_el_link` ✅
2. Si ese producto tiene foto, entonces la foto va arriba del mensaje; si no tiene, va solo texto y botones. — prueba: `test_caso2_foto_arriba_solo_si_el_producto_la_tiene` ✅
3. Si Meta rechaza el mensaje con botones (o el texto pasa de 1024 letras), entonces se manda el texto normal
   con el link, como hoy. — prueba: `test_caso3_si_meta_rechaza_los_botones_sale_el_texto_con_el_link` ✅
4. Si la plática va por el número central de IaRadio, o el bot le pasó la pregunta al dueño, o la plática está
   en pausa, entonces no salen botones (igual que hoy). — prueba: `test_caso4a/4b/4c (central, pregunta al dueño, pausa)` ✅
5. Si el cliente toca **🛒 Lo quiero**, entonces se crea el pedido con ese producto (cantidad 1) y el bot pide
   el nombre de una vez, sin preguntar "¿quieres hacer un pedido?". — prueba: `test_casos5_6_lo_quiero_arranca_el_pedido_y_ofrece_su_nombre` ✅
6. Si el cliente tiene nombre en WhatsApp (p. ej. "Juan Pérez"), entonces al pedir el nombre sale el botón
   **✅ Juan Pérez**; tocarlo o escribir otro nombre sirven igual. — prueba: `test_casos5_6_… + test_caso6_sin_nombre_en_whatsapp_no_hay_boton_y_puede_escribirlo` ✅
7. Si el negocio entrega a domicilio, entonces después del nombre salen **🏠 A domicilio** y **🏪 Recojo en
   tienda**; "A domicilio" pide la dirección y "Recojo" salta directo al pago. Si el negocio no entrega, no se
   pregunta: es para recoger (como hoy). — prueba: `test_caso7_con_domicilio… / test_caso7_recojo_en_tienda… / test_caso7_sin_domicilio…` ✅
8. Al preguntar cómo paga, salen **💵 Efectivo**, **💳 Tarjeta** y **🏦 Transferencia**, y el pedido guarda
   "Efectivo" / "Tarjeta" / "Transferencia" (sin el dibujito). Después llega la confirmación al cliente y el
   aviso del pedido al dueño, igual que hoy. — prueba: `test_caso8_pago_con_botones_cierra_el_pedido_y_avisa_al_dueno` ✅
9. Si el cliente toca **❓ Otra pregunta**, entonces el bot contesta "¡Claro! ¿Qué te gustaría saber? 😊" sin
   gastar IA y sin crear pedido. — prueba: `test_caso9_otra_pregunta_invita_a_preguntar_sin_ia_ni_pedido` ✅
10. Si el cliente toca **Lo quiero** pero ese producto ya se dio de baja, entonces el bot le dice que ya no está
    disponible y no crea pedido. — prueba: `test_caso10_producto_dado_de_baja_no_crea_pedido` ✅
11. Si el cliente toca **Lo quiero** con otro pedido a medias, entonces el pedido a medias se cancela y empieza
    el nuevo con este producto (no se guarda "🛒 Lo quiero" como su nombre). — prueba: `test_caso11_lo_quiero_con_pedido_a_medias_empieza_uno_nuevo` ✅
12. Si el cliente escribe "quiero pedir" (sin botón), el pedido sigue como hoy pero las preguntas de "¿lo
    confirmas?", entrega y pago también llevan botones. — prueba: `test_caso12_pedido_escrito_tambien_lleva_botones` ✅

## Fuera de alcance
- Cantidades distintas de 1 (el dueño lo ajusta al confirmar con el cliente).
- Botones en el chat web (`/sitio`, `/mi`): ya tiene sus propias tarjetas.
- Varios productos en una sola respuesta (sin botones: no se adivina cuál quiere).
- El agente del cliente en WhatsApp (sigue apagado).
- Negocios sin número propio (atienden por el central): siguen como hoy.

## Riesgos y costos
- **Meta:** los botones de respuesta solo van dentro de la plática que abrió el cliente (24 h): no son
  plantillas, no cuestan más, no requieren aprobación. Cada paso del pedido es el mismo número de mensajes que hoy.
- **Producción, todos los negocios:** si Meta rechaza el interactivo, cae al texto de hoy.
- Solo toca web (`adRadio`); worker y beat se redespliegan igual con el push.

## Plan técnico
- `meta_service.send_whatsapp_reply_buttons`: parámetro opcional `header_image_url` (encabezado de imagen).
- `inbound_pipeline`: `ButtonsFn` acepta la foto; al final, si hay producto mencionado y `send_buttons`, manda
  con botones en vez de `send`. Antes de la máquina de pedidos: tap de "Lo quiero" / "Otra pregunta".
  Producto del tap = el último link `/p/{negocio}/{producto}` en las respuestas recientes del bot (sin Redis).
  Sin estado nuevo: `collecting_address` primero pregunta domicilio/recoger (escribir la dirección de una vez también sirve); los pasos de pedido con opciones usan botones.
- Choque encontrado al construir: "lo quiero" es palabra de canje de cupón (coupon_service). Solo el título exacto del botón ("🛒 Lo quiero", con dibujito) cuenta como tap; escrito sigue canjeando cupón.
- `product_link_service`: sacar el producto del último link (`offered_product`).
- `meta_incoming._send_buttons`: pasa la foto.
- Pruebas: `tests/test_product_buttons_whatsapp.py` (base y Redis reales, Meta e IA simuladas).

## Prueba real (la hace el dueño)
1. Desde tu WhatsApp (…3182) a CityCell: "¿tienen bocinas?" (dar de alta la bocina otra vez antes).
2. Debe salir la respuesta con **🛒 Lo quiero** y **❓ Otra pregunta**.
3. Toca **Lo quiero** → nombre con botón → **🏠 A domicilio / 🏪 Recojo** → pago con botones.
4. Te llega el aviso del pedido por el central y aparece en Pedidos. Luego cancela el pedido y borra la bocina.
