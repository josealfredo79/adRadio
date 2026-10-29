# Campañas Fase A: arreglar lo roto antes del bot que pregunta

Fecha: 2026-10-28 · Estado: construida (sin subir)

## Qué y para quién
Antes de que el bot ofrezca "Audio de radio" o "Varios días" (plan `docs/PLAN-CAMPANAS-SIMPLES.md`
v2), lo que ya existe tiene que llegar de verdad. Hoy 5 de los 7 estilos de audio no le llegan a
nadie por web, el tope de cuñas no frena y las series prometen días que no cumplen.
Para el dueño del negocio (lo que manda llega) y para IaRadio (los planes se respetan).

## Decisiones del dueño
- Arranque → 1 audio y 1 imagen de prueba al mes; después, candado "Disponible desde Negocio".
- Series (Secuencia, Saga, Parrilla) → se ocultan hasta que manden por días de verdad (Fase D).

## Casos (cada uno lleva su prueba)
1. Si el dueño manda una campaña de audio en cualquiera de los 7 estilos (Cuña clásica,
   Comunitaria, Cápsula, Trivia, Mini Historia, Alerta, Estacional) "gratis por web", entonces al
   cliente con avisos le suena "🔊 Toca para escucharla" y en su chat queda **la cuña que el dueño
   escuchó**. — prueba: `test_caso1_los_7_estilos_llegan_por_web_con_la_cuna` (×7) ✅
2. Si la manda también por WhatsApp (con chip), entonces sale **esa misma cuña** como nota de voz,
   no el texto leído por otra voz. — prueba: `test_caso2_por_whatsapp_sale_la_misma_cuna_no_el_texto` (×7) ✅
3. Antes de mandar, el alcance de esos 7 estilos cuenta a los clientes de la web (hoy dice que por
   web no se puede). — prueba: `test_caso3_el_alcance_cuenta_la_web_en_los_7_estilos` (×7) ✅
4. Si un dueño de Negocio ya mandó 4 audios este mes, entonces al generar el 5.º ve "Ya usaste
   las 4 cuñas de radio de tu plan este mes…" (hoy nunca frena). — prueba: `test_caso4_negocio_la_quinta_cuna_del_mes_no_se_genera` ✅
5. Si un dueño de Arranque no ha mandado audio este mes, entonces puede generar, escuchar y mandar
   **1**; al intentar el 2.º ve "Tu audio de prueba de este mes ya lo usaste. El audio es del plan
   Negocio." — prueba: `test_caso5_arranque_manda_un_audio_de_prueba_y_el_segundo_no` ✅
6. Lo mismo con la imagen (Banner): Arranque puede mandar **1 al mes**; la vista previa siempre
   se puede ver; la 2.ª no se manda y dice por qué. — prueba: `test_caso6_arranque_una_imagen_de_prueba_y_la_vista_previa_siempre`, `test_caso6_desde_negocio_las_imagenes_no_tienen_tope` ✅
7. Si un dueño de Arranque abre "Más opciones", entonces Audio e Imagen dicen "1 de prueba este
   mes" (o el candado si ya la usó), no "Tu plan no incluye esta función". — prueba: `caso 7` ×2 (CampanasFaseA.test.tsx) ✅
8. Secuencia y Saga ya no aparecen en "Más opciones", ni el botón "Parrilla Semanal". Las que ya
   existen siguen en la lista y se pueden ver o borrar. — prueba: `caso 8` (CampanasFaseA.test.tsx) ✅

## Fuera de alcance
- El bot que pregunta (Fase B web, Fase C WhatsApp).
- Foto real del producto con texto encima (Fase B).
- Series mandadas por días y Parrilla por web (Fase D); Voces del Barrio (Fase E).
- Cambiar precios o textos de la página de planes.

## Riesgos y costos
- Toca el envío de campañas (worker de Celery): se despliegan web + worker + beat juntos.
- Por WhatsApp los 7 estilos mandan nota de voz como hoy hacen Cuña y Comunitaria: mismo costo de
  Meta (solo con chip). Por web es gratis. `revisor-dinero` revisa antes de subir.
- El tope empieza a frenar: un negocio de Negocio que hoy manda más de 4 cuñas al mes dejará de
  poder. Hay que saber antes si alguno lo hace (script de solo lectura con `!`).
- La prueba de Arranque usa audio (edge-tts, gratis) e imagen dibujada en el servidor (gratis).

## Plan técnico
- `backend/app/services/campaign_reach.py`: `RADIO_MODES` = los 7; `WEB_MODES` los incluye.
- `backend/app/workers/tasks.py` (`schedule_campaign`): los 7 van por `send_radio_messages`.
- `backend/app/api/v1/campaigns.py` (`generate-radio-ad`): contar por
  `ab_test->>'campaign_mode'` en `RADIO_MODES` y solo campañas que salieron del borrador;
  Arranque/trial: 1 al mes.
- Imagen en Arranque: permitir `banner/preview`; frenar al mandar (`resume` / `start_campaign`)
  la 2.ª imagen del mes. Mismo freno para audio al mandar.
- `backend/app/core/plans.py` / `deps.py`: "1 de prueba al mes" para Arranque en audio e imagen.
- `frontend/src/pages/campaigns/types.ts`, `CampaignListHeader.tsx`, `ModeSelector`: ocultar
  Secuencia, Saga y "Parrilla Semanal"; textos de candado / "1 de prueba".

## Prueba real (la hace el dueño)
1. Brave, cuenta CityCell (Arranque) → Campañas → Nueva campaña → Más opciones → Cápsula del Día →
   genera y escucha la cuña → Crear → enviar → **Uno** → 9531953182 → Mandar gratis por web.
2. Chrome (`/mi`, cliente 9531953182): en el chat de CityCell aparece la cuña y se escucha igual.
3. Brave: intentar una 2.ª cuña este mes → debe decir que la de prueba ya se usó.
4. En "Más opciones" ya no aparecen Secuencia, Saga ni "Parrilla Semanal".

## Resultado (2026-10-28)
- Backend: 1886 pruebas OK, 1 saltada (`scripts/test_local.sh`); Fase A: 27.
- Frontend: 47 archivos, 267 pruebas OK; tsc y eslint limpios.
- Prompts: sin cambios (no aplica probar_ia).
- Antes de subir: correr con `!` el script de solo lectura que dice qué negocios frenaría el tope.
- revisor-dinero: "Subir"; sin envíos ni cobros de Meta de más (los 5 estilos usan el mismo
  `_offer_or_queue` y ahora mandan la cuña ya hecha en vez de una voz por cliente). Huecos del
  tope arreglados: crear la cuña ya programada, envío masivo desde Contactos (ahora con
  contenido + preflight) y la Parrilla automática (no cuenta). El tope cuenta desde la subida
  (`COUNT_FROM`) para no frenar a nadie por cuñas viejas. Queda (bajo): los borradores no cuentan;
  en los 5 estilos por WhatsApp ya no va cupón por cliente (igual que Cuña y Comunitaria).
