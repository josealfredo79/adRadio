# Plan: campañas simples, todos los tipos (web, Copiloto y WhatsApp)

Fecha: 2026-10-28 (v2; la v1 del 2026-10-27 está en git, 011b05a) · Estado: plan rediseñado,
decisiones tomadas · Cada fase va por la skill `nueva-funcion`.

## Lo que pidió el dueño
Que **todos** los tipos de campaña (no solo la promo de texto) se puedan hacer igual de fácil
que la "Nueva promo" en 3 toques: en la web, en el Copiloto web y en el Copiloto por WhatsApp,
con texto, audio o imagen.

## Ya hecho (v1)
- Fase 0 (b5d3a0d, 80bfb48): alcance sin chip = 0 por WhatsApp; el generador ve el catálogo.
- Fase 1 (31a92d5): "Nueva promo" en 3 toques, solo texto; "¿A quién?" Todos / Compraron / Uno.
- Fase 2 (5a05b74): el Copiloto crea y manda promos de texto (`send_promo`).
- Arreglos de la prueba real 2026-10-28 (c9fb9b3, 9deb126, ad196bb, c0d15ff local): aviso si el
  texto promete un % sin cupón, "sale mañana a las 8:00" de noche, texto en buen español.

## Los 12 tipos, vistos por dentro (revisado en el código 2026-10-28)
Para el dueño son 12 botones, pero en realidad son **4 formatos** y 1 caso aparte:

| Formato | Tipos de hoy | Qué recibe el cliente |
|---|---|---|
| **Texto** | Regular | Un mensaje |
| **Imagen** | Banner Visual | Una imagen con la promo |
| **Audio** | Cuña clásica, Radio Comunitaria, Cápsula del Día, Trivia, Mini Historia, Alerta de Servicio, Cuña Estacional | Una cuña de radio; cambia solo el **estilo** del guion |
| **Serie** | Secuencia (3 mensajes), Saga (4 episodios), Parrilla Semanal (1 por día) | Varios mensajes en días distintos |
| Aparte | Voces del Barrio | No es un anuncio: junta audios de clientes y arma una historia |

### Fallas encontradas (hay que arreglarlas antes de simplificar)
1. **Secuencia y Saga no se mandan por días.** El envío elige UNO de los 3 o 4 mensajes al azar
   para cada cliente y lo manda una vez (`campaign_ops.send_regular_messages`,
   `random.choice(messages_list)`). La pantalla promete "días 1, 3 y 5" y "4 episodios semanales".
2. **Cápsula, Trivia, Mini Historia, Alerta y Estacional nunca llegan por web**, y por WhatsApp no
   mandan la cuña que el dueño escuchó: `schedule_campaign` solo trata como audio a
   `radio`/`comunitaria`; los otros 5 caen al envío de texto (`WEB_MODES` tampoco los incluye).
   Un negocio sin chip conectado, como CityCell, no le llega a nadie con estos 5.
3. **El tope de cuñas por mes no funciona.** `generate-radio-ad` cuenta campañas con
   `type` = radio/cápsula/…, pero el tipo que se guarda siempre es promo/recordatorio/evento:
   cuenta 0 y nunca frena ("Negocio: 4 al mes" es en la práctica sin límite).
4. **La Parrilla Semanal solo va por WhatsApp** (`send_parrilla_messages` no usa la web).
5. **Voces del Barrio solo va por WhatsApp** (`supports_web` lo excluye): los clientes mandan notas
   de voz al número del negocio.

### Lo que ya existe y se reusa
- Audio: guion con la cadena de modelos gratis + voz `edge-tts` (gratis) + subir a R2
  (`radio_service`, `POST /campaigns/generate-radio-ad`). 7 estilos ya escritos en
  `radio/scripts.py`.
- Imagen: cartel dibujado en el servidor (`banner_service.generate_banner_png`, gratis) con texto
  de la IA; imagen de Google Imagen (`imagen_service.generate_flyer`, **cuesta por imagen**);
  fotos del catálogo y fotos que el dueño manda por WhatsApp (`save_owner_photo`).
- Web: `_push_campaign` ya manda imagen en la notificación y audio en la tarjeta del chat.
- WhatsApp del dueño (número central): el Copiloto ya manda texto, botones y **notas de voz**
  (`send_platform_audio`); falta mandar **imagen** (`send_platform_image` no existe).
- Planes (`core/plans.py`, `deps.FEATURE_PLAN`): audio e imagen desde Negocio; series desde
  Crecimiento. Arranque (CityCell) hoy solo texto.

## Diseño: una sola "Nueva campaña"
Los mismos 3 pasos de hoy, con **un toque más** para el formato:

1. **¿Qué quieres anunciar?** (escrito o con voz).
2. **¿Cómo?** → `Texto` · `Imagen` · `Audio` · `Serie`. La IA propone uno según lo que dijo el
   dueño ("dato curioso de pantallas" → Audio, estilo Cápsula); él puede cambiarlo.
   - **Audio**: debajo, chips de estilo con nombres sencillos: Anuncio · Consejo · Dato curioso ·
     Trivia · Historia · Aviso · De temporada. La voz la elige la IA.
   - **Imagen**: foto del producto del catálogo (o la que mande) con la promo encima; si no hay
     foto, cartel de colores.
   - **Serie**: "3 mensajes en una semana" · "4 semanas (radionovela)" · "Un programa diario".
     Cada pieza puede ser texto o audio.
3. **Vista previa como la ve el cliente** (se lee, se escucha o se ve) + "¿A quién?" + cupón +
   "Mandar gratis por web" / "también por WhatsApp" (solo con chip).

**Voces del Barrio** sale de aquí y se vuelve su propio botón: "Pide opiniones a tus clientes".

En los 3 lugares es lo mismo:
- **Web**: el modal de 3 toques con el paso "¿Cómo?".
- **Copiloto web**: "manda un audio de 2x1 en micas a los que compraron" → vista previa en el chat
  (con reproductor o imagen) → botones Mandar / Otra versión / Cancelar.
- **Copiloto por WhatsApp**: igual, y la vista previa le llega al dueño como **nota de voz** o
  **imagen** por el número central (gratis: él acaba de escribir, la plática está abierta).

"Más opciones" se queda (A/B, programar fecha, plantillas) hasta que todo lo simple esté probado.

## Fases
### Fase A — Arreglar lo roto (≈ 1 día) · revisor-dinero
1. Los 7 estilos de audio se mandan como cuña: por web (tarjeta con audio) y por WhatsApp (la nota
   de voz que el dueño escuchó). Falla 2.
2. Tope de cuñas por mes contando por `campaign_mode`, no por `type`. Falla 3.
3. Secuencia, Saga y Parrilla se ocultan de la pantalla hasta la Fase C (decisión del dueño).
4. Arranque: 1 audio y 1 imagen de prueba al mes, luego candado.

### Fase B — Audio e imagen en los 3 toques de la web (≈ 2 días)
Paso "¿Cómo?" con Texto / Imagen / Audio y los 7 estilos; la IA propone formato y estilo;
vista previa que se escucha o se ve; candado del plan donde aplique.

### Fase C — Series reales (≈ 2 días) · revisor-dinero · probablemente migración
Secuencia, Saga y Parrilla mandan cada pieza en su día (tarea de Celery por pieza), por web y por
WhatsApp, respetando horario humano, "¿A quién?" y pausas anti-baneo. Pantalla: "Pieza 2 de 3
sale el jueves".

### Fase D — Copiloto con todos los formatos (≈ 1.5 días) · revisor-dinero
`send_promo` acepta formato, estilo y serie; vista previa con audio/imagen en la web y por
WhatsApp (`send_platform_image` nuevo). Confirmación con botones como hoy.

### Fase E — Voces del Barrio simple (≈ 2 días, decidir)
"Pide opiniones a tus clientes": el cliente graba desde `/mi` (web, gratis) además de WhatsApp.

### Fase F — Medir (de la v1)
"La vieron N · Tocaron ¡La quiero! N · Cobraste a N" por campaña.

## Decisiones del dueño (2026-10-28)
- **Planes**: Arranque puede hacer **1 audio y 1 imagen de prueba al mes**; después, candado
  "Disponible desde Negocio". Negocio y arriba como hoy (con el tope de cuñas ya funcionando).
- **Imagen**: **foto real del producto** (catálogo o la que mande por WhatsApp) con la promo y el
  precio encima; si no hay foto, cartel de colores. Nada de imagen inventada por IA en lo simple.
- **Series**: se **ocultan en la Fase A** hasta que la Fase C las mande por días de verdad.
- **Voces del Barrio**: **sí, al final** (Fase E), con grabación desde `/mi` además de WhatsApp.

## Riesgos
- Las series mandan varios mensajes por cliente: más costo de Meta por WhatsApp y más riesgo de
  baneo. Por web es gratis.
- Producción sin staging: lo nuevo convive con "Más opciones"; no se borra nada.
- Pruebas reales con "¿A quién? → Uno" (cuenta CityCell, cliente 9531953182 en `/mi`).

## Orden recomendado
A → B → D (texto/audio/imagen ya en los 3 lugares) → C → E → F. En paralelo, conectar el chip
(coexistencia) para que todo esto también salga por WhatsApp.
