# Plan: campañas simples, todos los tipos (web, Copiloto y WhatsApp)

Fecha: 2026-10-28 (v2; la v1 del 2026-10-27 está en git, 011b05a) · Estado: plan rediseñado,
decisiones tomadas · Cada fase va por la skill `nueva-funcion`.

## Lo que pidió el dueño
Que **todos** los tipos de campaña (no solo la promo de texto) se hagan muy fácil, con muy poca
fricción, y que **el bot vaya preguntando**: en la web, en el Copiloto web y en el Copiloto por
WhatsApp, con texto, audio o imagen.

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

## Diseño: el bot te va preguntando (decisión del dueño 2026-10-28)
Todo tipo de campaña se hace **platicando**: el bot pregunta una cosa a la vez, casi siempre
con botones, y se salta lo que ya sabe o puede adivinar. Es el **mismo bot** en los 3 lugares:
el panel web (botón "Nueva campaña" abre la plática), el Copiloto web y el Copiloto por
WhatsApp (número central). "Más opciones" se queda escondido para lo avanzado (A/B, fecha).

### Las preguntas (solo las que falten)
1. **¿Qué quieres anunciar?** — escrito o con voz. Si el dueño ya lo dijo ("manda un audio de
   2x1 en micas a los que compraron"), el bot salta directo a la vista previa.
2. **¿Cómo se lo mando?** — la IA propone el formato y lo pone primero:
   `Texto` · `Con foto` · `Audio de radio` · `Varios días` · (`Pedir opiniones`).
3. Solo si hace falta, una pregunta del formato:
   - Audio → estilo: `Anuncio` · `Consejo` · `Dato curioso` · `Trivia` · `Historia` · `Aviso` ·
     `De temporada` (la IA sugiere uno; la voz la elige sola).
   - Con foto → `Foto de <producto del catálogo>` · `Mando una foto` · `Cartel de colores`.
   - Varios días → `3 mensajes en una semana` · `4 semanas (radionovela)` · `Uno diario 7 días`.
   - Pedir opiniones → `¿Sobre qué?` (Voces del Barrio).
4. **Vista previa**: el texto, la imagen o el audio **como le llega al cliente** (por WhatsApp
   llega como nota de voz o imagen al dueño). Botones: `Así está bien` · `Otra versión` ·
   `Cambiar algo`.
5. **¿A quién?** — `Todos` · `Los que compraron` · `Uno` (por nombre o teléfono).
6. **¿Le pones descuento?** — solo si el texto habla de descuento o el dueño lo pidió:
   `Sí, 10%` · `15%` · `20%` · `No`.
7. **Mandar** — `Mandar gratis por web` (y `También por WhatsApp, aprox $X` solo con chip).
   De noche: "Sale mañana a las 8:00".

Una campaña normal: **3 a 4 toques**. Si el dueño lo dice todo de una vez: **1 toque** (Mandar).

### Reglas para que haya poca fricción
- Nunca preguntar lo que se puede adivinar: nombre, tipo, voz, colores, horario los pone el bot.
- Siempre botones; escribir solo para "¿Qué quieres anunciar?" y "Cambiar algo".
- WhatsApp: máximo 3 botones por mensaje; para 4–7 opciones, lista de WhatsApp
  (`send_platform_list`, nueva) o "Más estilos".
- Se puede dejar a medias y seguir después ("¿Seguimos con tu promo de micas?"), guardada como
  borrador.
- Candados por plan dentro de la plática: "El audio es del plan Negocio. Te queda 1 de prueba
  este mes, ¿lo usamos?".

### Una sola pieza por dentro
Un "armador de campañas" en el backend (`app/domain/campaign_builder.py`) guarda el paso en que
va cada dueño y decide la siguiente pregunta. La web y WhatsApp solo lo dibujan (botones web o
botones/listas de WhatsApp). Así no se separan (lección de `6d27525`). Reusa `send_promo`,
`generate-radio-ad`, `banner_service`, `campaign_reach`, `start_campaign`.

## Fases
### Fase A — Arreglar lo roto (≈ 1 día) · revisor-dinero
1. Los 7 estilos de audio se mandan como cuña: por web (tarjeta con audio) y por WhatsApp (la nota
   de voz que el dueño escuchó). Falla 2.
2. Tope de cuñas por mes contando por `campaign_mode`, no por `type`. Falla 3.
3. Secuencia, Saga y Parrilla se ocultan de la pantalla hasta la Fase D.
4. Arranque: 1 audio y 1 imagen de prueba al mes, luego candado.

### Fase B — El armador que pregunta + texto, foto y audio en la web (≈ 3 días)
`campaign_builder` con las preguntas 1–7 para Texto, Con foto y Audio (7 estilos); "Nueva
campaña" del panel y el Copiloto web lo usan. La promo de 3 toques de hoy pasa a ser este flujo.

### Fase C — El mismo armador por WhatsApp (≈ 1.5 días) · revisor-dinero ✅ construida (2026-10-29)
Botones y listas por el número central; vista previa como nota de voz o imagen
(`send_platform_image`, `send_platform_list` nuevos); retomar a medias. La nota de voz sigue con la
promo rápida. Ver `docs/specs/2026-10-29-campana-que-pregunta-whatsapp.md`.

### Fase D — Varios días de verdad (≈ 2 días) · revisor-dinero · probablemente migración
Secuencia, Saga y Parrilla mandan cada pieza en su día, por web y WhatsApp, con horario humano,
"¿A quién?" y pausas anti-baneo; entran al armador como "Varios días".

### Fase E — Pedir opiniones (Voces del Barrio) (≈ 2 días)
Entra al armador; el cliente graba desde `/mi` (web, gratis) además de WhatsApp.

### Fase F — Medir (de la v1)
"La vieron N · Tocaron ¡La quiero! N · Cobraste a N" por campaña.

## Decisiones del dueño (2026-10-28)
- **Planes**: Arranque puede hacer **1 audio y 1 imagen de prueba al mes**; después, candado
  "Disponible desde Negocio". Negocio y arriba como hoy (con el tope de cuñas ya funcionando).
- **Imagen**: **foto real del producto** (catálogo o la que mande por WhatsApp) con la promo y el
  precio encima; si no hay foto, cartel de colores. Nada de imagen inventada por IA en lo simple.
- **Series**: se **ocultan en la Fase A** hasta que la Fase D las mande por días de verdad.
- **Voces del Barrio**: **sí, al final** (Fase E), con grabación desde `/mi` además de WhatsApp.

## Riesgos
- Las series mandan varios mensajes por cliente: más costo de Meta por WhatsApp y más riesgo de
  baneo. Por web es gratis.
- Producción sin staging: lo nuevo convive con "Más opciones"; no se borra nada.
- Pruebas reales con "¿A quién? → Uno" (cuenta CityCell, cliente 9531953182 en `/mi`).

## Orden recomendado
A → B → C (todo menos series ya platicando en web y WhatsApp) → D → E → F. En paralelo,
conectar el chip (coexistencia) para que las campañas también salgan por WhatsApp a clientes.
