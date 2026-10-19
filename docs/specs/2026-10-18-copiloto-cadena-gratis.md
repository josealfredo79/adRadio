# Copiloto con la cadena de modelos (gratis primero)

Fecha: 2026-10-18 · Estado: construida

## Qué y para quién
El Copiloto del dueño (panel, voz y WhatsApp al número central) dependía solo de Claude: el 18-oct se acabó el saldo de Anthropic y el Copiloto se cayó para todos. Ahora usa la misma cadena que el bot: Groq → Cloudflare → Gemini → Mistral → OpenRouter → Claude al final.

## Decisiones del dueño
- ¿A quién se enciende? → A todos ya (hoy está caído para todos).
- Ventas con modelos gratis → Se registran al momento y se muestra Deshacer, como hoy (sin confirmación extra).
- Orden de la cadena → la misma del bot, Claude al final ("debe funcionar con la cadena que diseñaste").

## Casos (cada uno lleva su prueba)
1. Si un modelo gratis contesta, entonces Claude no se llama. — prueba: `test_free_model_answers_without_claude` ✅
2. Si el dueño dice "cobré 85 a Juan" y el modelo gratis pide la herramienta, entonces la venta se registra con la herramienta de siempre y el modelo redacta la respuesta con el resultado real. — prueba: `test_free_model_runs_tools_and_sees_results` ✅
3. Si el primer modelo gratis falla (error, cuota, se atora), entonces se prueba el siguiente sin perder lo ya hecho en el turno (no se registra la venta dos veces). — prueba: `test_provider_fails_mid_turn_next_one_continues` ✅
4. Si todos los gratis fallan, entonces se usa Claude como hoy. — prueba: `test_all_free_fail_falls_back_to_claude` ✅
5. Si todos fallan (incluido Claude sin saldo), entonces el dueño ve "Tuve un problema…" y no un error. — prueba: `test_everything_fails_friendly_reply` ✅
6. Si la acción pide confirmación (campaña, cupón, cita, cambios del negocio), entonces sale la tarjeta de confirmar igual que hoy, venga del modelo que venga. — prueba: `test_free_model_confirm_tool_returns_card` ✅
7. Si el dueño confirma una acción, entonces el mensaje "listo" también lo redacta la cadena gratis (no solo Claude). — prueba: `test_confirmed_result_uses_chain` ✅
8. Si un modelo gratis pide una herramienta con datos mal formados (JSON roto), entonces se le devuelve el error para que lo corrija, sin tronar. — prueba: `test_bad_tool_arguments_returned_as_error` ✅
9. (agregado al probar con IA real) Si Gemini pide una herramienta, entonces en la siguiente vuelta se le regresa su firma (si no, la rechaza), y esa firma nunca llega a Claude. — prueba: `test_gemini_signature_goes_back_and_never_reaches_claude` ✅
10. (agregado) Cloudflare no se usa para el Copiloto (elige mal las herramientas). — prueba: `test_cloudflare_is_skipped_for_tools` ✅
11. (agregado) En el Copiloto, Gemini va primero y Groq después, para no gastar el tope por minuto de Groq que usa el bot de los clientes. — prueba: `test_gemini_goes_first_for_tools` ✅

## Fuera de alcance
- El agente del cliente (customer_agent.py): ya cae a los flujos fijos si Claude falla; pasarlo a la cadena va aparte.
- Aviso de saldo bajo de Anthropic en salud-bot.
- Cambiar los textos o herramientas del Copiloto.

## Riesgos y costos
- Modelos gratis eligen peor la herramienta o el monto: las ventas tienen Deshacer y las acciones grandes siguen con confirmación.
- Las herramientas pesan ~3,300 tokens por llamada: con la cuota gratis por minuto de Groq puede saltar al siguiente proveedor más seguido.
- Producción sin staging. Solo cambia el web (el Copiloto corre en la API); el worker usa el mismo código para WhatsApp → desplegar web y worker juntos (Railway lo hace solo con push).

## Plan técnico
- `backend/app/services/llm_client.py`: nueva `tool_completion()` — misma cadena, con herramientas. Recibe mensajes en formato Anthropic (bloques tool_use/tool_result) y los traduce al formato OpenAI para los gratis; devuelve texto + llamadas a herramientas normalizadas. Así si cambia de proveedor a media vuelta, el historial sirve igual.
- `backend/app/services/copilot_service.py`: el loop usa `tool_completion()` en vez de Claude directo; `_phrase_confirmed_result` usa `chat_completion()`.
- Pruebas nuevas en `backend/tests/test_copilot_chain.py`; ajustar las que simulaban el cliente de Claude.

## Prueba con IA real (2026-10-18, llaves de producción, sin base)
7 frases: "cobré 85 a Juan", "vendí 50", "¿cuánto llevo hoy?", "deshacer", "Juan me debe 50" (no debe cobrar), "agrega una funda a 120", "hola".
- Gemini gemini-3.5-flash-lite: 7/7, ~0.8 s; segunda vuelta OK ("Cobré 85 a Juan Pérez. Acumulado hoy: 170…") tras arreglar la firma.
- Groq gpt-oss-120b: acierta, pero 429 por tope de tokens/minuto desde el 2º mensaje → va después de Gemini.
- Cloudflare Llama 3.3: 3/7 (update en vez de create, "null" como texto, get_bot_status a un "hola") → fuera del Copiloto.
- OpenRouter: ling-3.0-flash-sante:free ya no existe (404) y gemma-4 saturado (429). Ojo: también afecta al nivel OpenRouter del bot.

## Prueba real (la hace el dueño)
1. Sin recargar Anthropic, en el panel de CityCell abre el Copiloto y escribe "cobré 85 a Cliente Prueba".
2. Debe contestar que registró $85 y mostrar Deshacer; luego "¿cuánto llevo hoy?" y "deshacer".
