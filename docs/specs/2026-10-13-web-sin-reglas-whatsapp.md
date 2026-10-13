# Campañas por web: sin reglas de WhatsApp, máximo 1 aviso al día

Fecha: 2026-10-13 · Estado: construida

## Qué y para quién
Hoy las campañas "Solo por web" pasan por las reglas anti-baneo de WhatsApp (48 h por
cliente, 7 días por segmento), que existen para que Meta no bloquee el número. En la web
ese riesgo no existe y el dueño no puede mandar una segunda promo (prueba del 13-oct:
"0 clientes por web" y "Podrás enviarla el 20 de octubre"). Pero muchas notificaciones
molestan y el cliente puede apagarlas. Regla nueva: que le **llegue** siempre, que
**suene** máximo una vez al día.

## Decisiones del dueño
- ¿Límite de avisos web? → Sí, 1 aviso (notificación de Chrome) al día por cliente; la promo llega siempre al chat y a Promociones.
- WhatsApp sigue con todas sus reglas anti-baneo.

## Casos (cada uno lleva su prueba)
1. Si mando una promo "Solo por web" a un cliente que recibió otra campaña hace menos de 48 h, entonces sí le llega (aparece en su chat y en Promociones). — prueba: `test_web_ignores_whatsapp_48h_cooldown` ✅
2. Si mando "Solo por web" al mismo grupo de clientes antes de 7 días, entonces no se bloquea ni al darle Enviar ni al enviarse. — prueba: `test_web_only_skips_segment_cooldown` ✅
3. Si es la primera promo del día para ese cliente, entonces le suena la notificación de Chrome. — prueba: `test_first_promo_of_the_day_rings` ✅
4. Si ya le sonó una promo hoy, entonces la siguiente no suena pero sí aparece en su chat y en Promociones, y cuenta como enviada. — prueba: `test_second_promo_same_day_arrives_silently` ✅
5. Si la promo anterior le sonó ayer (hora de México), entonces la de hoy sí suena. — prueba: `test_promo_rings_again_next_day` ✅
6. Si ya le sonó una promo hoy, entonces las respuestas del dueño desde el Inbox le siguen sonando. — prueba: `test_owner_reply_still_rings_after_promo` ✅
7. Si mando "Solo por web", entonces eso no le cuenta a WhatsApp: no arranca las 48 h del cliente ni los 7 días del grupo para una campaña por WhatsApp después. — prueba: `test_web_send_does_not_start_whatsapp_cooldowns` ✅
8. Si mando "Enviar a todos", entonces a los de WhatsApp se les siguen aplicando sus reglas (48 h y 7 días). — prueba: `test_whatsapp_part_keeps_its_rules` ✅
9. Antes de enviar, el dueño ve cuántos la reciben por web y cuántos de ellos sin sonar porque ya tuvieron aviso hoy. — prueba: `test_reach_counts_silent_web` + SendCampaignModal.test.tsx (4 casos, incl. solo "Solo por web" si nadie va por WhatsApp) ✅

## Fuera de alcance
- Mandar a la tarjeta (en silencio) a clientes que NO activaron las notificaciones.
- Límite configurable por el dueño (queda fijo en 1 al día).
- Horario: las campañas siguen saliendo solo en horas hábiles (ya existe; aplica también a web).

## Riesgos y costos
- Nada cobrado por Meta. El cambio quita reglas solo en el camino web; el de WhatsApp no se toca.
- Toca el worker (envío de campañas): desplegar web + worker juntos.

## Plan técnico
- `campaign_ops.py`: `_push_campaign(ring=…)` en los 3 envíos (normal, banner, radio): sin `_is_contact_active`; si ya sonó una promo hoy (mensaje "[PUSH]" de hoy, hora de México), guarda "[WEB] <campaña>" sin notificación; no toca `last_campaign_sent_at`.
- `tasks.py` `schedule_campaign` y `send_block_explain.preflight_campaign_send`: con `web_only`, sin el bloqueo de 7 días y sin registrar el envío del grupo.
- `campaign_reach.py`: web = clientes con avisos (sin las 48 h); `web_silent` = cuántos ya sonaron hoy.
- `SendCampaignModal.tsx`: "X por notificación web — gratis (Y sin sonar: ya tuvieron aviso hoy)".

## Resultado
- Backend: 796 pruebas de campañas/chat/copiloto (incluye 9 nuevas en test_web_without_whatsapp_rules.py) con Postgres y Redis locales.
- Frontend: todas las de vitest + tsc limpio.
- Extra: si nadie va por WhatsApp, la ventana ya no ofrece "Enviar a todos" (pasaba por las reglas de WhatsApp sin necesidad).

## Prueba real (la hace el dueño)
1. CityCell → Campañas → la "Promo Micas" → ▶ → debe decir 1 por web (1 sin sonar) → "Solo por web".
2. En la tarjeta de "Tú (prueba)" con el chat abierto: la burbuja nueva aparece sola, sin notificación de Chrome.
3. Mañana: otra promo "Solo por web" → esta sí suena.
