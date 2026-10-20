# Cobrar hablándole al Copiloto + atajos en "Cobrar"

Fecha: 2026-10-17 · Estado: construida

## Qué y para quién
Registrar cada cobro a mano es mucho trabajo para un dueño con fila en el mostrador (lo vio el dueño en la prueba de
"Cobré $___"). Ahora puede decirlo: "cobré 85 a Ana" al Copiloto (panel, voz o WhatsApp), o cobrar en 2 toques con
montos y clientes recientes a la vista.

## Decisiones del dueño
- El Copiloto guarda el cobro directo (sin "¿sí?") y ofrece "deshacer".
- Montos rápidos: los 4 que más cobra el negocio; sin ventas aún: $20, $50, $100, $200.

## Casos (cada uno lleva su prueba)
1. Si el dueño le dice al Copiloto "cobré 85 a Ana" y solo hay una Ana, entonces queda la venta de $85 a Ana con su
   sello, y el Copiloto contesta con el monto, el cliente, el sello y cuánto lleva hoy, y le recuerda que puede decir
   "deshacer". — prueba: `test_copiloto_caso1_cobre_85_a_ana_saves_with_stamp_and_today` ✅
2. Si dice "vendí 120" sin cliente, entonces queda una venta sin cliente de $120. — prueba: `test_copiloto_caso2_sale_without_customer_and_amount_with_words` ✅
3. Si hay varias Anas, entonces no guarda nada y pregunta cuál (nombre y últimos 4 dígitos); si una se llama
   exactamente "Ana", usa esa. — prueba: `test_copiloto_caso3_several_matches_asks_and_saves_nothing_unless_exact`, `test_copiloto_name_plus_last_digits_picks_that_customer` ✅
4. Si no encuentra al cliente, entonces no guarda nada y ofrece registrarlo sin cliente o darlo de alta con su teléfono;
   si el dueño da nombre y teléfono, lo da de alta (sin duplicar) y cobra. — prueba: `test_copiloto_caso4_not_found_offers_options_then_registers_new`, `test_copiloto_courtesy_titles_and_today_tool` ("don Juan" → Juan Pérez) ✅
5. Si dice "deshacer" o "me equivoqué", entonces se borra su último cobro de hoy con su sello; si dice cuál ("borra
   el de 50", "el de Beto"), se borra ese; si hay varios así, pregunta cuál y no borra nada; si no hay, se lo dice.
   (Cambio 2026-10-19: antes solo el último y solo 15 min; en la prueba real el dueño no pudo corregir.) — prueba:
   `test_copiloto_caso5_undo_takes_the_last_sale_of_today`, `test_copiloto_caso5b_undo_the_one_the_owner_names` ✅
6. Si el monto no es válido (0, negativo, más de $100,000), entonces no guarda y explica por qué. — prueba: `test_copiloto_caso6_bad_amount_is_explained` (4 montos) ✅
7. Funciona igual por WhatsApp (número central) y por voz, porque es el mismo Copiloto. — prueba: `test_copiloto_caso7_tools_are_registered_and_run_without_confirmation` ✅
8. En "Cobrar" aparecen 4 montos rápidos (los más cobrados, o $20/$50/$100/$200) que llenan el monto con un toque. — prueba: `test_atajos_caso8_quick_amounts_default_then_most_charged`, `caso 8 (copiloto)` ✅
9. En "Cobrar" aparecen los últimos 5 clientes a los que se les cobró, para tocarlos sin buscar. — prueba: `test_atajos_caso9_recent_customers_newest_first_without_repeats`, `caso 9 (copiloto)` ✅

Agregado al construir: "¿cuánto llevo hoy?" → herramienta `get_sales_today` (sin ella el Copiloto contestaba con los
pedidos). Fiados ("me debe 50") NO se registran como cobro.

## Prueba con la IA de verdad (Claude, 2026-10-17)
9 de 9 bien: "cobré 85 a Ana", "vendí 120", "me pagaron trescientos de don Juan", "cobre 45 … a la señora Mari",
"deshacer", "la de 1234" tras la pregunta de cuál Ana, "Ana me debe 50" (no cobra, explica), "¿cuánto vendí hoy?",
y la respuesta tras guardar ("$85 cobrados a Ana López (…1234) — sello sumado. Llevas $497.50 en 4 ventas hoy.
¿Me equivoqué? Di 'deshacer'"). Primera corrida: 1 falla (registraba el fiado) y 2 detalles ("don Juan", "¿cuánto
vendí?") → corregidos.

## Fuera de alcance
- Cobrar con terminal (Clip, Mercado Pago).
- Escanear el QR de la tarjeta del cliente.
- Que el bot de clientes registre ventas (solo el dueño cobra).

## Riesgos y costos
- Cada cobro por el Copiloto es una llamada a Claude (ya con caché y tope diario del Copiloto).
- Por WhatsApp: el dueño escribe primero, así que la respuesta es mensaje de servicio (1,000 gratis al mes por número).
- Sin migración.

## Plan técnico
- `backend/app/services/copilot_sales_tools.py`: herramientas `record_sale` y `undo_sale` (usan sales_service).
- `backend/app/services/copilot_service.py`: registrar las herramientas (ejecución inmediata) y la regla en el prompt.
- `backend/app/services/sales_service.py` + `api/v1/sales.py`: `GET /sales/shortcuts` (montos y clientes recientes).
- `frontend/src/pages/CashierPage.tsx`: montos rápidos y clientes recientes.

## Prueba real (la hace el dueño)
1. Copiloto en el panel (cuenta CityCell): escribe o di "cobré 85 a Cliente Prueba". Debe contestar con el monto,
   el cliente y "¿Me equivoqué? Di 'deshacer'". Luego di "deshacer".
2. Por WhatsApp: desde el WhatsApp registrado como "Tu WhatsApp personal" de CityCell, escríbele al número central de
   IaRadio "vendí 50" (o mándalo en nota de voz). Debe contestar igual.
3. Pregúntale "¿cuánto llevo hoy?".
4. En Cobrar: deben verse 4 montos rápidos ($20/$50/$100/$200 al principio) y abajo de la búsqueda "Recientes" con los
   clientes a los que ya les cobraste.
