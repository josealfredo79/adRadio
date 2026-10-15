# Seguimiento automático de interesados

Fecha: 2026-10-15 · Estado: construida (sin desplegar)

## Qué y para quién
Hoy, si un cliente pregunta por un producto, un precio o una cita y no compra, nadie lo retoma. IaRadio le
escribe **una vez**, solo, cerca de las 20 horas, con un mensaje corto sobre lo que preguntó ("¿Todavía
te interesa la funda? Te la aparto"). Si no hay cómo escribirle gratis, se le avisa al dueño.

## Decisiones del dueño
- ¿A quién? → Interesados (plática tibia o caliente) que no hicieron cita, pedido ni canje después.
  (Pregunta sin contestar; se tomó la recomendada.)
- ¿Cuántas veces y cuándo? → Una sola vez, ~20 h después de su último mensaje; nunca de 9 pm a 9 am.
- ¿Sin avisos web y con WhatsApp cerrado (más de 24 h)? → No se le escribe; va en el resumen de las
  8 am del dueño.
- ¿Automatizaciones del dueño? → No por ahora (queda anotado).
- Decisión técnica (cambiable): **encendido para todos**, con interruptor por negocio en Configuración.
  Por la web es gratis y es un solo mensaje.

## Casos (cada uno lleva su prueba)
1. Si un cliente preguntó (plática tibia o caliente), no agendó, no pidió ni canjeó, y su último
   mensaje fue hace ~20 h, entonces IaRadio le escribe un mensaje corto sobre lo que preguntó. — prueba: `test_casos1_2_10_interesado_con_avisos_web_recibe_su_seguimiento_en_el_chat` ✅
2. Si el cliente tiene avisos web, entonces el mensaje le llega a su chat web con aviso en el
   celular (gratis) y queda en la plática del Inbox. — prueba: `test_casos1_2_10_…` ✅
3. Si no tiene avisos web pero escribió por WhatsApp hace menos de 24 h, entonces le llega por
   WhatsApp (texto normal, gratis, dentro de la ventana). — prueba: `test_caso3_sin_avisos_pero_whatsapp_abierto_llega_por_whatsapp`, `test_si_el_aviso_web_no_llega_cae_a_whatsapp_si_esta_abierto` ✅
4. Si no tiene avisos web y su WhatsApp ya está cerrado, entonces no se le escribe y el dueño lo ve en
   su resumen de las 8 am: "Estos clientes preguntaron y no compraron: Ana, Beto…". — prueba: `test_caso4_sin_canal_gratis_no_se_le_escribe_y_va_al_resumen_del_dueno` (web cerrada y WhatsApp de 30 h) ✅
5. Si después de preguntar agendó, pidió o canjeó, entonces no se le escribe. — prueba: `test_caso5_si_ya_agendo_no_se_le_escribe` ✅
6. Si la plática es fría (solo saludó o dio las gracias), entonces no se le escribe. — prueba: `test_caso6_platica_fria_no_se_le_escribe` ✅
7. A un cliente se le da seguimiento **una sola vez por semana** como máximo. — prueba: `test_caso7_una_vez_por_semana` ✅
8. Entre 9 pm y 9 am (hora de México) no se manda nada; por la web se manda en cuanto den las 9 am. — prueba: `test_caso8_de_noche_no_se_manda_y_por_la_web_sale_a_las_9_am` ✅
9. No se le escribe si se dio de baja, si el dueño pausó el bot con él, si el negocio está en pausa
   (prueba vencida) o si el dueño apagó el seguimiento en Configuración. — prueba: `test_caso9_no_se_le_escribe` (baja, bot pausado, negocio en pausa, dueño lo apagó) ✅
10. Si el cliente contesta el seguimiento, entonces lo atiende el agente como siempre (con su historial). — prueba: `test_casos1_2_10_…` (el seguimiento queda en la plática que leen el bot y el agente) ✅
11. Si la IA falla al escribir el mensaje, entonces se manda uno fijo: "¡Hola, Ana! ¿Pudiste resolver lo
    que buscabas? Aquí estoy para ayudarte 🙂". — prueba: `test_caso11_si_la_ia_falla_se_manda_el_mensaje_fijo` (error, vacío y demasiado largo) ✅

Extras: `test_nombre_para_saludar` ✅ ("Don Raúl" → "Raúl"); interruptor en Configuración:
`frontend/src/__tests__/FollowupSettingsCard.test.tsx` ✅; ruta de Celery: `tests/test_celery_routing.py` ✅.

Prueba con IA real (2026-10-15, cadena del bot desde local, terminó en Claude porque Groq y OpenRouter dieron
404 con las llaves locales): 8/8 casos bien — mencionan lo que preguntó, sin descuentos inventados ni datos
personales (teléfono y dirección del cliente no se repiten). Corregido: "Hola Don" → salta títulos.

## Fuera de alcance
- Automatizaciones (secuencias) que arma el dueño: siguen como hoy.
- Plantillas de WhatsApp cobradas para escribir fuera de las 24 h.
- Segundo seguimiento (a los 3 días) y cupones automáticos en el seguimiento.

## Riesgos y costos
- Web: gratis. WhatsApp: solo dentro de las 24 h (sin plantilla, sin costo de marketing).
- IA: el mensaje lo escribe la cadena barata (Groq primero; Claude solo de respaldo).
- Toca a todos los negocios (encendido por defecto): un solo mensaje por cliente por semana.
- Celery beat: tarea nueva cada 15 min → desplegar web, worker y beat (se despliegan juntos).
- Migración: `users.followup_enabled` (true) y `contacts.last_followup_at`.

## Plan técnico
- `alembic/versions/0075_followup.py`: las dos columnas.
- `app/services/followup_service.py`: busca candidatos, decide canal, escribe el mensaje (llm_client,
  respaldo fijo), lo manda y lo guarda en la plática; lista para el resumen del dueño.
- `app/workers/tasks.py` + `celery_app.py`: tarea `send_followups` cada 15 min.
- `app/services/owner_alerts.py`: línea "preguntaron y no compraron" en el resumen de las 8 am.
- `app/schemas` + `/me`: `followup_enabled`; `frontend`: interruptor en Configuración.
- Pruebas: `tests/test_followup.py` (base y Redis reales; push, Meta y la IA simulados).

## Prueba real (la hace el dueño)
1. En incógnito, como cliente de CityCell con avisos web activados, preguntar por un producto y no pedir.
2. ~20 h después debe llegar el aviso al celular con un mensaje sobre ese producto.
3. En el Inbox de CityCell, la plática muestra el seguimiento.
