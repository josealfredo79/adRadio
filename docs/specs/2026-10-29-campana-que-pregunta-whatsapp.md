# Campaña que pregunta por WhatsApp (Fase C)

Fecha: 2026-10-29 · Estado: construida

## Qué y para quién
El dueño arma una campaña **escribiéndole al número central de IaRadio por WhatsApp**, con la
misma plática de una pregunta a la vez que ya existe en la web: texto, foto o audio, a quién, cupón
y mandar. Sirve para que no tenga que abrir el panel. Reusa `app/domain/campaign_builder.py`; aquí
solo se agrega el transporte de WhatsApp (botones, listas, foto y nota de voz).
Ver `docs/PLAN-CAMPANAS-SIMPLES.md` (Fase C) y `docs/specs/2026-10-29-campana-que-pregunta.md`.

## Decisiones del dueño
- Si pide la campaña con **nota de voz**, sigue la promo rápida de siempre (una vista previa y
  "Sí, mándala"), no la plática paso a paso (2026-10-29).
- Si **escribe** "manda una promo de 2x1", la plática le pregunta cómo mandarla, a quién y cupón,
  saltándose lo que ya dijo (2026-10-29).
- La vista previa se manda como lo que verá el cliente: **nota de voz** para la cuña, **imagen**
  para la foto y **texto** para el mensaje.
- Para salir a medias escribe "salir" o "cancelar": la campaña queda como borrador y se retoma
  después, igual que en la web.
- Mandar sigue siendo con los mismos botones: gratis por web y, solo con chip, también por
  WhatsApp con su costo aproximado.

## Casos (cada uno lleva su prueba)
1. Si escribe "haz una campaña de 2x1 en micas", entonces el Copiloto abre la plática en WhatsApp
   con la primera pregunta y sus opciones. — prueba: `test_caso1_abre_la_platica_por_whatsapp` ✅
2. Si la pregunta tiene 3 opciones o menos, entonces llegan como **botones**; si tiene más, como
   **lista** de hasta 10; lo que toca se entiende como su respuesta. — prueba:
   `test_caso2_botones_hasta_tres_y_lista_cuando_hay_mas` ✅
3. Si elige `Audio de radio`, entonces ve los 7 estilos en lista y, al elegir, **escucha la cuña**
   como nota de voz antes de decir "Así está bien". — prueba:
   `test_caso3_la_cuna_llega_como_nota_de_voz` ✅
4. Si elige `Con foto` y manda una foto, entonces esa foto se usa para la campaña y la vista previa
   es **la misma imagen** que le llegará al cliente. — prueba:
   `test_caso4_su_foto_se_usa_y_la_vista_previa_es_la_imagen` ✅
5. Si elige `Texto`, entonces ve el mensaje con los precios de su catálogo y los botones de siempre.
   — prueba: `test_caso5_texto_con_botones_de_vista_previa` ✅
6. Si elige `Uno`, entonces escribe el nombre o teléfono y le aparecen las coincidencias en lista
   para escoger. — prueba: `test_caso6_uno_busca_y_elige_de_la_lista` ✅
7. Si el mensaje promete un %, entonces el cupón se pregunta con botones `Sí` · `No`; si no, salta
   a mandar. — prueba: `test_caso7_cupon_con_botones` ✅
8. Al final ve el alcance y los botones `Mandar gratis por web` (y `También por WhatsApp`, con
   chip); al tocar uno, la campaña sale y la plática se cierra. En WhatsApp el botón solo cabe en
   20 letras, así que el costo aproximado va en el texto de arriba. Un "Sí" o "También" suelto no
   manda nada (puede ser la respuesta a un cliente): solo el botón o la frase completa. — prueba:
   `test_caso8_manda_desde_el_boton_y_cierra_la_platica`,
   `test_caso8b_con_chip_el_costo_va_en_el_texto_y_manda_por_los_dos` y
   `test_caso8c_un_si_o_tambien_suelto_no_manda_la_campana` ✅
9. Si dejó una campaña a medias y vuelve a pedir una, entonces ve "¿Seguimos con tu promo…?" con
   `Seguir` · `Empezar otra`; `Seguir` retoma en el paso donde iba. — prueba:
   `test_caso9_retoma_el_borrador_donde_iba` ✅
10. Si escribe "salir" o "cancelar" a media plática, entonces no se manda nada, la campaña queda
    como borrador y el Copiloto deja de preguntar. — prueba: `test_caso10_salir_deja_el_borrador` ✅
11. Si manda una foto **en el paso de la foto**, entonces se usa para la campaña, no se guarda como
    producto nuevo del catálogo. — prueba: `test_caso11_foto_en_el_paso_no_se_vuelve_producto` ✅
12. Si pide la campaña con **nota de voz**, entonces sigue la promo rápida (una vista previa y
    "Sí, mándala"), no la plática. — prueba: `test_caso12_nota_de_voz_sigue_la_promo_rapida` ✅
13. Si Meta rechaza los botones o la lista, entonces manda el texto con las opciones escritas y el
    dueño puede contestar escribiéndolas. — prueba: `test_caso13_si_meta_rechaza_las_opciones_va_el_texto` ✅
14. Si no hay Redis (no se puede recordar la plática entre mensajes), entonces no abre el armador y
    lo manda al panel, como ya pasa con las confirmaciones. — prueba:
    `test_caso14_sin_redis_no_abre_el_armador` ✅
15. Si tiene una pregunta de cliente pendiente y la plática abierta, entonces lo que escriba (aunque
    sea "Sí" o "También") sigue en el armador y no se le manda al cliente; para contestarle, responde
    citando el aviso. — prueba: `test_un_si_del_armador_no_se_le_manda_al_cliente` ✅

**Resultado:** 19 pruebas en `backend/tests/test_campaign_builder_whatsapp.py` (+ el ruteo en
`test_owner_questions.py`); suite completa del backend en verde (**1933 passed, 1 skipped**) y
frontend en verde (**263**) sobre base y Redis locales recreados (sin tocar producción). Las
pruebas de la Fase B (`backend/tests/test_campaign_builder.py`, 27) y las de la promo rápida
(`test_copilot_promo.py`, 51) siguen en verde.

## Fuera de alcance
- La plática paso a paso por **nota de voz** (se queda la promo rápida; se puede hacer después).
- `Varios días` (Fase D), `Pedir opiniones` (Fase E) y medir (Fase F).
- Plantillas nuevas de Meta, programar fecha, A/B y editar la foto desde WhatsApp.
- Mandar la vista previa desde el chip del dueño: la previa sale del número central.

## Riesgos y costos
- Toca mensajes con Meta (botones y listas) y el envío de campañas: `revisor-dinero` antes de subir.
- Los botones/listas solo se pueden mandar dentro de la ventana de 24 h (el dueño acaba de
  escribir, así que sí); si Meta los rechaza, cae al texto con las opciones escritas.
- La cuña se convierte a OGG/Opus para que llegue como nota de voz (igual que las respuestas de
  voz); si la conversión falla, se manda el audio tal cual y, si Meta también lo rechaza, la
  pregunta sigue en texto con los botones.
- Mandar por WhatsApp sigue costando lo mismo que hoy y solo aparece con chip conectado.
- Producción sin staging: el cambio se prueba con el número de pruebas y una cuenta de Arranque.

## Plan técnico
- `backend/app/services/platform_whatsapp.py`: `send_platform_list` (hasta 10 filas) y
  `send_platform_image` (imagen por link), con respaldo a texto (la lista numerada para que el
  dueño conteste el número o el título).
- `backend/app/services/copilot_service.py`: `build_campaign` también en el canal `whatsapp`
  (escrito); `send_promo` se queda solo para `voz`. Regla del Copiloto por canal.
- `backend/app/services/copilot_whatsapp_service.py`: estado `builder` en Redis (la campaña y el
  paso completo, tal como lo devuelve `campaign_builder.handle`); enruta texto, botón, lista y foto
  al armador; dibuja el paso (botones/lista, texto, imagen o nota de voz); "salir"/"cancelar" deja
  el borrador. Los títulos de los botones se recortan a 20 letras y los de la lista a 24; el costo
  de WhatsApp se mueve al texto porque no cabe en el botón. En "mandar" solo valen el botón o las
  frases completas: "sí"/"también" sueltos no disparan el envío pagado.
- `backend/app/services/owner_question_service.py`: si la plática de campañas está abierta, el
  mensaje va al armador **antes** de clasificarlo como respuesta a una pregunta de cliente (un
  "Sí" del cupón no debe contestarle a un cliente); los mensajes citados sí siguen yendo al cliente.
- Reusa: `campaign_builder.handle`, `send_platform_buttons`, `send_platform_audio`,
  `save_owner_photo`, `_to_ogg` y el candado de "Mandar" una sola vez.
- Pruebas: `backend/tests/test_campaign_builder_whatsapp.py` (nuevo, 17) y ajuste de
  `test_campaign_builder.py`/`test_copilot_promo.py` por el cambio de herramientas.

## Prueba real (la hace el dueño)
1. Con su teléfono, escribir al número central: "haz una campaña de 2x1 en micas este viernes".
2. Elegir `Audio de radio` → un estilo → escuchar la cuña → `Así está bien` → `Todos` → `Mandar
   gratis por web`.
3. Ver que la cuña llega al chat de un cliente de prueba y que la campaña ya no está en borrador.
4. Repetir con `Con foto`: mandar una foto y ver la imagen con la promo encima.
5. Pedir una campaña por nota de voz: debe seguir la promo rápida de un solo mensaje.
