# Entrega a domicilio: sí o no

Fecha: 2026-10-20 · Estado: construida

## Qué y para quién
Hoy el bot acepta pedidos a domicilio aunque el negocio no entregue (lo encontró la simulación del
2026-10-20: "Pedido #0001 confirmado… a domicilio" en una estética que dice "No hacemos servicio a
domicilio"). El dueño tendrá un ajuste claro, y el bot solo ofrecerá domicilio si está encendido.

## Decisiones del dueño
- ¿Cómo lo dice el dueño? → Interruptor "Entrego a domicilio" en Configuración y el Copiloto lo cambia
  si el dueño se lo pide.
- ¿Negocios que nunca lo dijeron? → Sin definir: el bot ofrece solo "para recoger"; si el cliente pide
  domicilio, dice que lo confirma con el negocio y avisa al dueño.
- ¿Más datos (costo, colonias)? → Solo sí/no por ahora.

## Casos (cada uno lleva su prueba)
1. Si el negocio **sí** entrega, entonces el agente pregunta "¿a domicilio o para recoger?" como hoy y
   acepta la dirección. — prueba: `test_caso1_delivers_asks_and_takes_the_address` ✅
2. Si el negocio **no** entrega y el cliente pide domicilio, entonces el agente dice que solo es para
   recoger en el local y ofrece el pedido así; ningún pedido queda a domicilio. — prueba: `test_caso2_no_delivery_offers_pickup_and_no_home_order` + `test_caso2y3_silent_switch_to_pickup_is_said_out_loud` ✅
3. Si el negocio **no lo ha definido** y el cliente pide domicilio, entonces el agente ofrece recoger,
   dice que lo confirma con el negocio y le avisa al dueño; ningún pedido queda a domicilio. — prueba: `test_caso3_undefined_consults_the_business_and_no_home_order` + `test_caso2y3_silent_switch_to_pickup_is_said_out_loud` ✅
4. Si el negocio no entrega (o no lo definió), entonces el agente nunca pregunta "¿a domicilio o para
   recoger?": da por hecho recoger. — prueba: `test_caso4_without_delivery_never_asks_home_or_pickup` ✅
5. Si el negocio no entrega, entonces los flujos de pedido de siempre (chat web sin agente y WhatsApp)
   se saltan la pregunta de dirección y el pedido dice "para recoger". — prueba: `test_caso5_web_flow_skips_the_address` + `test_caso5_whatsapp_flow_skips_the_address` ✅
6. Si el dueño mueve el interruptor en Configuración, entonces queda guardado y el bot lo respeta en el
   siguiente mensaje. — prueba: `test_caso6_settings_switch_is_saved_and_the_agent_follows_it` ✅
7. Si el dueño le dice al Copiloto "ya no hago entregas" (o "ya entrego a domicilio"), entonces el
   Copiloto lo propone, pide confirmación y cambia el ajuste. — prueba: `test_caso7_copilot_changes_it_with_confirmation` ✅
8. Si un negocio existe desde antes, entonces queda "sin definir" (nadie queda encendido por sorpresa). — prueba: `test_caso8_existing_businesses_start_undefined` ✅

## Fuera de alcance
- Costo de envío, zonas o colonias de entrega, tiempo de entrega.
- Deducir el ajuste del texto de la información de cada negocio.
- Avisar a los dueños actuales que existe el ajuste (se puede hacer después con el Copiloto o un aviso).

## Riesgos y costos
- Producción sin staging; migración aditiva (columna nueva que acepta vacío): el código viejo la ignora.
- **Cambio de comportamiento para todos:** negocios que sí entregan y no lo han dicho dejarán de recibir
  pedidos a domicilio por el bot hasta encenderlo (decisión del dueño: "sin definir" = solo recoger).
- Sin mensajes nuevos de Meta: el aviso del caso 3 es el mismo `avisar_al_dueno` de hoy (1 cada 30 min).
- Toca web y worker (WhatsApp): desplegar los tres servicios juntos (lo hace `deploy`).

## Plan técnico
- `backend/alembic/versions/0077_delivers_home.py` + `backend/app/models/user.py`: `delivers_home`
  booleano que acepta vacío (vacío = sin definir). Skill `migracion`.
- `backend/app/schemas/profile.py`, `schemas/auth.py`: se lee y se cambia por `PATCH /me`.
- `backend/app/services/customer_agent.py`: la descripción de `proponer_pedido` y las reglas del prompt
  dependen del ajuste; `_tool_proponer_pedido` rechaza "domicilio" si no está encendido (con el mensaje
  para la IA según "no" o "sin definir").
- `backend/app/services/widget_order_service.py` y `inbound_pipeline.py`: sin domicilio, saltan
  `collecting_address` y el resumen dice "para recoger".
- `backend/app/services/copilot_business_tools.py`: `update_bot_info` acepta `delivers_home` (con la
  confirmación de siempre).
- `frontend/src/components/AgentSettingsCard.tsx` (+ `AuthContext.tsx`): interruptor "Entrego a domicilio".
- Verificación: pruebas por caso, `cliente-simulado` con los escenarios de domicilio en los tres estados.

## Resultado (2026-10-20)
- Pruebas en `backend/tests/test_home_delivery.py`; suite completa 1763 bien (una de login dio 429 por
  repetir corridas seguidas; con Redis limpio pasa). Frontend: tsc limpio, 243 pruebas bien.
- Migración 0077 probada: sube, baja y vuelve a subir; `alembic check` sin diferencias en `delivers_home`.
- Simulador con IA real en los tres estados: no entrega → "Aquí no hay entrega a domicilio"; sin definir →
  avisa al equipo y ofrece recoger; sí entrega → pedido con dirección.
- Ajuste al construir: con "sin definir" el modelo cambiaba a "recoger" sin decírselo al cliente. Ahora, si
  el mensaje del cliente pide entrega, `proponer_pedido` le indica decirlo y (sin definir) avisa al negocio
  él mismo, sin depender del modelo.

## Prueba real (la hace el dueño)
1. Configuración → tarjeta "Agente inteligente": el interruptor "Entrego a domicilio" está apagado.
2. "Probar como cliente": **"quiero un shampoo, me lo traen a mi casa?"** → debe ofrecer recoger y decir
   que lo confirma con el negocio.
3. Encender el interruptor y repetir → ahora pregunta la dirección.
4. En el Copiloto: **"ya no hago entregas a domicilio"** → confirma con Sí y el interruptor se apaga.
