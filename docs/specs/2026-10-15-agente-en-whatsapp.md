# Agente del cliente en WhatsApp

Fecha: 2026-10-15 · Estado: construida (sin desplegar)

## Qué y para quién
El agente que ya atiende el chat web (agenda, pide, cancela, canjea premios, siempre con un "sí" del
cliente) atiende también a los clientes que le escriben al WhatsApp **propio del negocio**. Hoy ningún
negocio tiene número propio conectado, así que se construye **apagado** y se enciende cuando el primero
se conecte.

## Decisiones del dueño
- ¿Construir ya aunque nadie lo use todavía? → Sí, apagado detrás de un interruptor.
- ¿Cómo confirma el cliente? → Botones Sí / No de WhatsApp (sin plantilla: van dentro de las 24 h).
- ¿"Cancelar" a secas? → Va al agente; la baja se queda con "baja", "stop", "salir" y "no quiero".

## Casos (cada uno lleva su prueba)
1. Si el interruptor está apagado, entonces WhatsApp contesta exactamente como hoy (flujos fijos y bot). — prueba: `test_caso1_apagado_contesta_como_hoy`, `test_caso1_solo_los_correos_del_interruptor` ✅
2. Si está encendido para ese negocio y el cliente escribe "quiero una cita mañana en la tarde",
   entonces el agente le ofrece horarios, propone la cita y le manda botones **Sí, confírmalo / No**. — prueba: `test_casos2_3_12_cita_con_botones_aviso_por_whatsapp_y_queda_en_el_inbox` ✅
3. Si el cliente toca "Sí, confírmalo" (o escribe "sí"), entonces la cita se crea y al dueño le llega
   el aviso diciendo **"desde WhatsApp"** (no "desde la web"). — prueba: `test_casos2_3_12_cita_con_botones_aviso_por_whatsapp_y_queda_en_el_inbox` ✅
4. Si toca "No", entonces no se crea nada y el agente le pregunta si necesita algo más. — prueba: `test_caso4_boton_no_no_crea_nada` ✅
5. Pedidos, cancelar cita o pedido y canjear premio funcionan igual que en la web, con los mismos
   candados (10 min para cancelar pedido, nunca dice "listo" sin hacerlo). — prueba: `test_caso5_pedido_por_whatsapp_avisa_al_dueno_con_el_canal`, `test_caso6_…` (cancelar cita); candados: `tests/test_customer_agent.py` ✅
6. Si el cliente escribe solo "cancelar" y tiene una cita próxima o un pedido recién hecho, entonces
   el agente le pregunta cuál cancelar (no lo da de baja). — prueba: `test_caso6_cancelar_a_secas_con_cita_va_al_agente_y_no_da_de_baja` ✅
7. Si escribe solo "cancelar" y no tiene nada activo, entonces se le contesta: "No tienes citas ni
   pedidos activos. Si quieres dejar de recibir mensajes, escribe BAJA". No se le da de baja. — prueba: `test_caso7_cancelar_a_secas_sin_nada_explica_como_darse_de_baja` ✅
8. "baja", "stop", "salir" y "no quiero" siguen dando de baja como hoy. — prueba: `test_caso8_las_demas_palabras_siguen_dando_de_baja` ✅
9. Si el agente le preguntó "¿lo confirmo?" y el cliente contesta "sí", ese "sí" es para el agente,
   aunque haya un recordatorio de cita esperando respuesta. — prueba: `test_caso9_el_si_es_del_agente_aunque_haya_un_recordatorio_esperando` ✅
10. Un "sí" a un recordatorio de cita confirma **la cita de ese cliente**, no la de otro cliente del
    mismo negocio (hoy el código no filtra por cliente: se arregla de paso). — prueba: `test_caso10_el_si_al_recordatorio_solo_confirma_la_cita_de_ese_cliente` ✅
11. Si Claude falla o tarda, entonces contestan los flujos fijos de siempre (como en la web). — prueba: `test_caso11_si_claude_falla_contestan_los_flujos_fijos` ✅
12. Lo que dice el agente y lo que contesta el cliente se guarda en la plática del Inbox, igual que hoy. — prueba: `test_casos2_3_12_cita_con_botones_aviso_por_whatsapp_y_queda_en_el_inbox` ✅
13. Si el dueño pausó el bot o está contestando desde su celular (coexistencia), el agente no se mete. — prueba: `test_caso13_bot_pausado_el_agente_no_se_mete` (coexistencia usa el mismo corte del inicio) ✅

Extra: `test_numero_central_sin_botones_no_usa_el_agente` ✅ (el central sigue con su bot de ventas).

Prueba con IA real: no se corrió; el único cambio de instrucciones fue "en su chat web" → "en su chat". El modelo y las herramientas son los mismos que se probaron en la web en producción el 2026-10-15.

## Fuera de alcance
- Encenderlo en producción para todos (se enciende cuando haya negocios con número propio).
- El número central de IaRadio: sigue con su bot de ventas y la redirección de clientes a la web.
- Notas de voz al agente (siguen por la transcripción y el flujo de siempre).
- Mensajes que el agente inicie solo (seguimiento): eso es la función del CRM, aparte.

## Riesgos y costos
- Meta: las respuestas van dentro de la ventana de 24 h abierta por el cliente → sin plantilla y sin
  costo de mensaje de marketing. Los botones interactivos no requieren aprobación.
- Costo de IA: ~US$0.008 por mensaje que atiende el agente (Claude Haiku), igual que en la web.
- Toca el camino de WhatsApp de todos los negocios: por eso va detrás del interruptor y el caso 1
  prueba que apagado no cambia nada.
- Despliegue: web (webhook de Meta) — el worker no cambia.

## Plan técnico
- `app/config.py`: `CUSTOMER_AGENT_WHATSAPP` = "" (apagado), "all", o correos de negocios separados
  por coma (para probar con uno).
- `app/services/meta_service.py`: `send_whatsapp_reply_buttons(to, body, buttons)` — mensaje
  interactivo con hasta 3 botones de respuesta.
- `app/services/customer_agent.py`: `channel` ("web" | "whatsapp") en el contexto; avisos al dueño
  "desde WhatsApp"; el prompt deja de decir "chat web"; `whatsapp_enabled(advertiser)`.
- `app/services/inbound_pipeline.py`: después de crear contacto y plática y del escalado a humano,
  antes del catálogo y los flujos fijos, llama al agente; si contesta, guarda en la plática y el
  Inbox y manda el texto (con botones si espera un sí). Un "sí" pendiente del agente se salta los
  manejadores de recordatorio. "cancelar" a secas sale de las palabras de baja cuando el agente está
  encendido (casos 6–8). El recordatorio de cita filtra por cliente (caso 10).
- `app/api/v1/webhooks_pkg/meta_incoming.py`: le pasa al pipeline la función de botones.
- Pruebas: `tests/test_customer_agent_whatsapp.py` con base y Redis reales; Claude y Meta simulados.

## Prueba real (la hace el dueño)
Requiere un negocio con número propio conectado (hoy ninguno). Cuando exista:
1. En Railway (adRadio): `CUSTOMER_AGENT_WHATSAPP=<correo del negocio>`.
2. Desde un teléfono que **no** sea el del dueño, escribirle al número del negocio: "quiero una cita
   mañana en la tarde" → elegir hora → tocar **Sí, confírmalo**.
3. Debe llegar la cita a Citas y el aviso al WhatsApp del dueño diciendo "desde WhatsApp".
4. Escribir "cancelar" → debe preguntar qué cancelar → confirmar con el botón.
