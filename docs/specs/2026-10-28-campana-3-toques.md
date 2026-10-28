# Campaña en 3 toques (Fase 1 de campañas simples)

Fecha: 2026-10-28 · Estado: construida

## Qué y para quién
El dueño manda una promo en tres pasos, casi sin escribir: dice qué quiere anunciar, la IA arma
el mensaje con su catálogo real y él toca "Mandar". Hoy el formulario tiene 12 modos y la mayoría
no lo necesita. Ver `docs/PLAN-CAMPANAS-SIMPLES.md`.

## Decisiones del dueño
- Clientes sin avisos web (y sin WhatsApp) → la promo **queda en su chat /mi** y en Promociones,
  sin notificación; la ven cuando entren. Gratis.
- "Los que compraron" → quien tenga un "Cobré" o un pedido cobrado en los **últimos 90 días**.
- Cupón → **botón opcional** "Agregar descuento" (10% / 15% / 20%); nunca se pone solo.
- Entrada → el botón **"Nueva campaña" abre los 3 pasos**; "Más opciones" abre el formulario de
  ahora, completo.

## Casos (cada uno lleva su prueba)
1. Si el dueño toca "Nueva campaña", entonces ve un solo campo "¿Qué quieres anunciar?" con
   micrófono, y un enlace "Más opciones" que abre el formulario completo de siempre. — ✅ `caso 1` (QuickCampaignModal.test), `test_caso1_lo_que_dice_el_dueno_se_vuelve_texto`
2. Si escribe o dice "2x1 en tacos el viernes", entonces la IA le muestra el mensaje armado con
   los precios de su catálogo (sin inventar) y él puede tocar "Otra versión" o editarlo. — ✅ `caso 2` (QuickCampaignModal.test)
3. Si no tiene catálogo, entonces el mensaje no trae precios inventados (ya cubierto en Fase 0). — ✅ cubierto en Fase 0 (sin cambio de prompt)
4. Si elige "¿A quién? → Todos", entonces la campaña va a todos sus clientes activos. — ✅ `test_caso4_todos_va_a_todos_los_activos`
5. Si elige "Los que compraron", entonces solo va a quien tenga un "Cobré" o pedido cobrado en
   los últimos 90 días; si no hay nadie, el botón "Mandar" se apaga y dice por qué. — ✅ `test_caso5_*` (3) + `caso 5` (QuickCampaignModal.test)
6. Si elige "Uno", entonces puede buscar al cliente por nombre o teléfono y la campaña va solo a él. — ✅ `test_caso6_uno_solo`, `test_caso6_busca_cliente_por_nombre_o_telefono`, `caso 6`
7. Antes de mandar ve la vista previa (como la verá el cliente) y el alcance: "A N les suena
   aviso · M la ven en su chat cuando entren · X por WhatsApp (Meta te cobra aprox $Y)". — ✅ `test_caso7_cuenta_aviso_chat_y_whatsapp_sin_guardar`, `caso 7 y 8`
8. Si no tiene WhatsApp conectado, entonces solo ve "Mandar gratis por web" y una nota
   "Conecta tu chip para mandar también por WhatsApp". — ✅ `test_caso8_sin_chip_nadie_por_whatsapp`, `caso 7 y 8`
9. Si tiene WhatsApp conectado, entonces ve "Mandar gratis por web" (principal) y "Mandar también
   por WhatsApp" con el costo aprox. — ✅ `test_caso9_con_chip_cuenta_whatsapp_y_costo`, `caso 9`
10. Si manda "gratis por web", entonces a quien activó avisos le suena la notificación y a los
    demás les queda en su chat sin sonar; nadie recibe WhatsApp y no se gasta saldo. — ✅ `test_caso10_*`, `test_web_only_campaign_end_to_end`, `caso 10`
11. Si toca "Agregar descuento 15%", entonces cada cliente recibe su cupón (por web o WhatsApp);
    si no lo toca, no hay cupón. — ✅ `test_caso11_*` (3), `caso 11`
12. Si "Mandar" falla (sin plan activo, regla de WhatsApp), entonces ve el motivo en palabras
    claras y la campaña queda guardada como borrador, sin perder lo escrito. — ✅ `test_caso12_sin_plan_activo_no_crea_y_dice_por_que`, `caso 12`
13. El "Solo por web" de las campañas hechas con "Más opciones" también deja la promo en el chat
    de quien no tiene avisos (antes no le llegaba nada). — ✅ `test_caso13_solo_por_web_se_manda_aunque_nadie_tenga_avisos`, `caso 13` (SendCampaignModal.test)

## Fuera de alcance
- Imagen, banner, cuña de radio o Voces del Barrio en el flujo simple (siguen en "Más opciones").
- Programar para otro día (sale en cuanto se toca "Mandar", en horario humano como siempre).
- Crear campañas desde el Copiloto o por WhatsApp (Fase 2).
- Dejar en el chat a quien no le pudo llegar el WhatsApp cuando se manda "también por WhatsApp".
- Resultados de la campaña ("la vieron N…", Fase 3).

## Riesgos y costos
- Toca el envío de campañas (worker de Celery): se despliegan web + worker + beat juntos.
- WhatsApp sigue costando lo mismo y solo sale si el dueño toca "también por WhatsApp" con chip
  conectado. `revisor-dinero` revisa el diff antes de subir (cupones + envío).
- "Uno" y "Los que compraron" son grupos nuevos: cuentan aparte para la pausa de 7 días de
  WhatsApp (no se confunden con "Todos").
- Producción sin staging: lo de "Más opciones" no se borra, solo se mueve.

## Plan técnico
- `backend/app/services/campaign_reach.py`: grupo `segment.bought_days` (ventas de los últimos N
  días) en `recipients_query`; el alcance cuenta `web_chat` (quedan en su chat sin sonar).
- `backend/app/workers/task_helpers/campaign_ops.py`: en "solo por web", quien no tiene avisos
  recibe la promo en silencio (`_push_campaign(ring=False)`) en lugar de nada; huella del grupo
  incluye `bought_days`.
- `backend/app/api/v1/campaigns.py`: `resume` con `web_only` ya no exige avisos activos si hay a
  quién dejarle la promo en el chat; vista previa de alcance antes de crear (`POST /campaigns/reach-preview`
  con texto + grupo) para mostrarla sin guardar borrador.
- `backend/app/api/v1/contacts.py`: búsqueda `q` por nombre o teléfono.
- `frontend/src/pages/campaigns/components/QuickCampaignModal.tsx` (nuevo): los 3 pasos; reusa
  `/generate-content`, `voiceRecorder` + `/voice-setup/listen`, `POST /campaigns`, `/resume`.
- `frontend/src/pages/campaigns/index.tsx`: "Nueva campaña" abre el nuevo; "Más opciones" abre
  `CreateCampaignModal`.

## Prueba real (la hace el dueño)
1. En una cuenta de prueba cuyo único cliente sea un teléfono tuyo (no el del dueño), abre ese
   teléfono en /mi y activa los avisos.
2. Campañas → Nueva campaña → di "2x1 en tacos el viernes" → revisa que los precios sean los
   de tu catálogo → ¿A quién? Uno → tu teléfono → Mandar gratis por web.
3. Debe sonar el aviso en el teléfono y aparecer en su chat; no debe llegar WhatsApp.

## Resultado (2026-10-28)
- Backend: 1818 pruebas OK, 1 saltada (`scripts/test_local.sh`). Frontend: 46 archivos, 259+ pruebas OK; tsc y eslint limpios.
- Prompts: sin cambios (el generador es el de Fase 0), no se corrió probar_ia.
- revisor-dinero: nada gasta saldo ni manda WhatsApp/Meta sin querer; arreglados sus puntos bajos
  (huella "compraron" sin días, validar segmento en PATCH e ids, límite 30/min en reach-preview,
  prueba aviso fallido → un solo cupón). Queda: re-mandar a mano una campaña web pausada duplica
  mensaje/cupón (ya existía; poco probable).
- Nota: "Nueva campaña" sigue apagado si el plan no tiene mensajes de WhatsApp, aunque la web sea gratis.
