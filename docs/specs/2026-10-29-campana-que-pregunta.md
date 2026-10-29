# Campaña que pregunta (Fase B: web y Copiloto web)

Fecha: 2026-10-29 · Estado: construida (sin subir)

## Qué y para quién
El dueño arma cualquier campaña de texto, foto o audio **platicando**: el bot pregunta una cosa a
la vez, con botones, y se salta lo que ya sabe. Sustituye a la "Nueva promo" de 3 toques en el
panel y es lo mismo que usa el Copiloto web. Ver `docs/PLAN-CAMPANAS-SIMPLES.md` (v2).

## Decisiones del dueño
- El bot va preguntando, todos los tipos, muy poca fricción (2026-10-28).
- Imagen = foto real del producto con la promo encima; si no hay foto, cartel de colores.
- Arranque: 1 audio y 1 imagen de prueba al mes (Fase A).
- Varios días y Pedir opiniones llegan en las Fases D y E; aquí no se ofrecen.

## Casos (cada uno lleva su prueba)
1. Si el dueño toca "Nueva campaña", entonces ve una plática: "¿Qué quieres anunciar?" con campo
   y micrófono (y "Más opciones" abajo). — prueba: `test_caso1_empieza_preguntando_que_anuncias`, `caso 1` (CampaignBuilderChat.test) ✅
2. Si escribe "2x1 en micas este viernes", entonces el bot pregunta "¿Cómo se lo mando?" con
   `Texto` · `Con foto` · `Audio de radio`, poniendo primero el que mejor le queda. — prueba: `test_caso2_pregunta_como_con_el_mejor_primero`, `caso 2` ✅
3. Si elige `Audio de radio`, entonces le ofrece el estilo con el sugerido primero (Anuncio,
   Consejo, Dato curioso, Trivia, Historia, Aviso, De temporada) y luego le pone **la cuña para
   escucharla**, con `Así está bien` · `Otra versión` · `Cambiar el texto`. — prueba: `test_caso3_audio_estilo_sugerido_y_la_cuna_para_escuchar`, `caso 3` ✅
4. Si elige `Con foto` y en su catálogo hay productos con foto que tienen que ver, entonces le
   ofrece esas fotos (hasta 3), `Subir una foto` y `Cartel de colores`; la vista previa es **su
   foto con la promo y el precio encima**. — prueba: `test_caso4_con_foto_ofrece_las_del_catalogo_y_pone_la_promo_encima`, `test_caso4_solo_abre_fotos_guardadas_por_iaradio`, `caso 4` ✅
5. Si elige `Texto`, entonces ve el mensaje con los precios de su catálogo y los mismos botones
   (Así está bien / Otra versión / Cambiar el texto). — prueba: `test_caso5_texto_con_catalogo_y_otra_version` ✅
6. Después pregunta "¿A quién?" `Todos` · `Los que compraron` · `Uno` (busca por nombre o
   teléfono). — prueba: `test_caso6_a_quien_y_uno_por_nombre` ✅
7. Si el texto promete un % o el dueño pidió descuento, entonces pregunta "¿Le pongo cupón de
   10%?" `Sí` · `No`; si no, no pregunta. — prueba: `test_caso7_cupon_solo_si_el_texto_promete_descuento` ✅
8. Al final ve el alcance ("A 1 cliente le suena aviso…") y `Mandar gratis por web` (y `También
   por WhatsApp, aprox $X` solo con chip). De noche dice "Sale mañana a las 8:00". — prueba: `test_caso8_alcance_mandar_gratis_por_web_y_de_noche`, `caso 8` ✅
9. Si lo dice todo de una vez ("manda un audio de dato curioso de 2x1 en micas a los que
   compraron"), entonces el bot salta directo a la vista previa y luego a Mandar. — prueba: `test_caso9_si_lo_dice_todo_salta_a_la_vista_previa_y_a_mandar` ✅
10. Si es Arranque y ya usó su audio (o imagen) de prueba del mes, entonces `Audio de radio` (o
    `Con foto`) sale con 🔒 y al tocarlo explica "Es del plan Negocio" sin gastar nada.
    — prueba: `test_caso10_arranque_sin_prueba_ve_candado_y_no_gasta`, `caso 10` ✅
11. Si cierra la plática a medias, entonces la campaña queda como borrador y al volver a "Nueva
    campaña" el bot pregunta "¿Seguimos con tu promo de micas?" `Seguir` · `Empezar otra`.
    — prueba: `test_caso11_a_medias_queda_borrador_y_se_retoma`, `caso 11` ✅
12. Si en el Copiloto web le pide "haz una campaña de…", entonces la misma plática aparece dentro
    del Copiloto con lo que ya entendió. — prueba: `test_caso12_en_el_copiloto_web_abre_la_misma_platica`, `test_del_copiloto_solo_se_queda_lo_que_dijo_el_dueno` ✅
13. Lo que se manda es lo que vio: la cuña que escuchó, la foto que vio con su texto (igual para
    todos los clientes) o el texto, por web y, con chip, por WhatsApp. — prueba: `test_caso13_la_foto_que_vio_es_la_que_se_manda_por_whatsapp` ✅

## Fuera de alcance
- Por WhatsApp (Fase C), Varios días (Fase D), Pedir opiniones (Fase E), medir (Fase F).
- Programar fecha, A/B y plantillas: siguen en "Más opciones".
- Imagen inventada por IA (Google Imagen): no se usa aquí.

## Riesgos y costos
- Audio: guion con la cadena gratis + voz edge-tts (gratis); tarda ~10–20 s → mensaje "Grabando
  tu cuña…". Foto: se dibuja en el servidor (gratis).
- WhatsApp solo con chip y botón aparte, como hoy; `revisor-dinero` antes de subir.
- Toca envío de campañas (foto fija en `send_banner_messages`): web + worker + beat juntos.
- Producción sin staging: "Más opciones" se queda; el modal de 3 toques se reemplaza.

## Plan técnico
- `backend/app/domain/campaign_builder.py` (nuevo): la plática como pasos. Guarda el paso en el
  borrador (`Campaign.ab_test["builder"]`), decide la siguiente pregunta y arma la respuesta
  `{text, choices[], input, preview{kind,text,image_url,audio_url}, reach}`. Sugerir formato y
  estilo: por palabras ("audio", "dato curioso", "foto"…) y por fotos del catálogo; sin llamada
  extra a la IA (más rápido; cambio respecto al plan original).
- `backend/app/api/v1/campaigns.py`: `POST /campaigns/builder` (empezar / contestar / retomar).
- `backend/app/services/banner_service.py`: `photo_banner_png(foto, texto, precio)`.
- `backend/app/workers/task_helpers/campaign_ops.py`: si la campaña trae foto fija
  (`ab_test.photo_fixed`), manda esa imagen y no dibuja una por cliente.
- Reusa: `generate_campaign_variants`, `generate_radio_script`/`generate_radio_ad`,
  `campaign_quota`, `campaign_reach`, `copilot_promo_tools.start_campaign`, `/copilot/photo`.
- `backend/app/services/copilot_service.py`: herramienta `build_campaign` que abre la plática con
  lo que ya entendió.
- `frontend/src/pages/campaigns/components/CampaignBuilderChat.tsx` (nuevo): burbujas + botones
  + reproductor + imagen; lo usan Campañas y `CopilotPage`.

## Prueba real (la hace el dueño)
1. Brave, CityCell → Campañas → Nueva campaña → "2x1 en micas este viernes" → `Audio de radio` →
   escucha → `Así está bien` → `Uno` → 9531953182 → `Mandar gratis por web`.
2. Chrome (`/mi` con 9531953182): llega la cuña al chat de CityCell.
3. Repetir con `Con foto` (otro mes o en una cuenta Negocio, por la prueba de Arranque).
4. Copiloto web: "haz una campaña de 10% en cargadores" → la plática aparece ahí mismo.

## Resultado (2026-10-29)
- Backend: 1903 pruebas OK, 1 saltada. Plática: 18 pruebas. Frontend: 47 archivos, 259 OK; tsc y eslint limpios.
- IA real, de punta a punta en base local (Gemini + edge-tts): texto con precio del catálogo ($80), cuña
  "Dato curioso" grabada, foto del producto con la promo y el precio encima, alcance correcto.
- Copiloto web con IA real: 5/6 abren la plática a la primera; "mándale a Lupe…" primero busca a Lupe.
  La IA ponía `format="text"` sin que el dueño lo dijera → `keep_said` lo quita.
- **edge-tts 7.2.8 ya no funciona** (Microsoft responde 403): sube a 7.3.1. Afecta también las cuñas y
  notas de voz que hoy están en producción.
- revisor-dinero: "Subir". Arreglado antes de subir: candado contra "Mandar" doble (salía doble y Meta
  cobraría doble), estilo/formato/cupón inventados en peticiones a mano.
- Ojo (no es de esta fase): el estilo "Dato curioso" puede afirmar datos no comprobados.
- Pruebas finales, 2.ª pasada (2026-10-29): faltaban los caminos que no son el feliz —cartel de
  colores, subir su propia foto, «100%» (la prueba se perdió al borrar la promo de 3 toques), sin
  clientes, mandar también por WhatsApp, candado de imagen de Arranque, borrador de más de una
  semana y que otro dueño no pueda seguir el borrador— y el endpoint `POST /campaigns/builder`.
  Plática: 27 pruebas. Backend 1913 OK, 1 saltada. Frontend 263 OK; tsc y eslint limpios.
