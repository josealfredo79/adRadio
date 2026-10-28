# Plan: campañas simples (web y WhatsApp)

Fecha: 2026-10-27 · Estado: plan analizado, sin aprobar · Cada fase va por la skill `nueva-funcion`.

## Problema
Mandar una promo hoy pide demasiadas decisiones a un dueño de negocio chico, y por WhatsApp
(Copiloto) no se puede crear una campaña.

## Lo que hay hoy (revisado en el código)
- **Web** (`frontend/src/pages/campaigns/components/CreateCampaignModal.tsx`, 636 líneas): nombre,
  tipo (5), modo (12: regular, banner, secuencia, saga, cuña, comunitaria, cápsula, trivia, mini
  historia, alerta, estacional, voces), plantilla guardada, cupón con horas, A/B con división y
  métrica. Todo en una sola pantalla.
- **Antes de enviar** (`SendCampaignModal.tsx` + `campaign_reach.py`): cuántos por web (gratis) y
  cuántos por WhatsApp con costo; botón "Solo por web — gratis". Esto está bien y se conserva.
- **Copiloto** (`copilot_service.py`): tiene `list_campaigns`, `get_campaign_stats`,
  `launch_campaign` (solo una que YA existe) y `create_coupon`. NO tiene `create_campaign`, aunque
  el docstring de `copilot_whatsapp_service.py` promete "manda la promo 2x1 a todos".
- **Generador de mensajes** (`claude_service.generate_campaign_variants`): solo recibe tipo,
  nombre del negocio e intención. **No ve el catálogo ni la base de conocimiento** → puede
  inventar precios o productos (rompe la regla "si no está en la base, no existe").
- **Envío por WhatsApp** (`meta_service.send_whatsapp`): sale del número PROPIO del negocio. Sin
  WhatsApp conectado devuelve `meta_not_connected`. No hay respaldo por el número central.
- **Alcance** (`campaign_reach`): **no revisa si el negocio tiene WhatsApp conectado**. A un
  negocio como CityCell le muestra "N por WhatsApp, $X" aunque esos mensajes nunca van a salir.
- **Fuera de 24 h** (`campaign_ops._offer_or_queue`): manda una plantilla para reabrir la plática
  (`meta_radio_invite_template_name` o `meta_utility_template_name`), que el dueño configura a
  mano. Sin ella, a ese cliente no le llega. Ya existe `meta_templates.create_template` (crea
  plantillas en el WABA del negocio desde la app): se puede reutilizar.
- **Crear** (`POST /campaigns`): exige nombre y mensaje; tipo dentro de 5 valores. Sirve tal cual
  para la versión simple si el front llena nombre/tipo solos.

## Decisión del dueño (2026-10-27)
Las campañas por WhatsApp salen **del número del chip del propio negocio** — es la única forma.
Nunca por el número central de IaRadio. Por eso conectar el chip (Embedded Signup con
**coexistencia**: el dueño sigue usando su app de WhatsApp Business en el celular) pasa a ser
pieza central del plan, no un extra. Ya está construido (73c0489, `coexistence_service.py`,
spec `docs/specs/2026-10-12-coexistencia.md`) pero apagado salvo admins/testers.

Lo que falta para encenderlo (ver memoria `project_meta_embedded_signup`):
- Suscribir en Meta → WhatsApp → Configuración → Webhooks: `smb_message_echoes`,
  `smb_app_state_sync`, `history`, `account_update`.
- Prueba real con un chip con WhatsApp Business en CityCell (contactos importados, bot se calla
  30 min cuando el dueño contesta desde su celular, campaña de prueba sale de su número).
- Luego `META_EMBEDDED_SIGNUP_ADMINS_ONLY=false` para todos.
- **Quién paga a Meta: la tarjeta del negocio** (decidido 2026-10-27). Con el plan no alcanza:
  marketing en México ≈ $0.73 MXN por mensaje (`campaign_reach.META_MARKETING_USD_MX` 0.0397 USD
  × 18.5; revisar tarifa vigente de Meta). Si los envíos del plan fueran todos plantillas pagadas:
  Arranque 150 → $110 de $449; Negocio 500 → $367 de $899; Crecimiento 1,500 → $1,101 de $1,799;
  Empresa 5,000 → $3,672 de $4,999; paquete "+500 envíos" a $99 costaría $367 (pierde $268).
  Además, como Tech Provider IaRadio no puede compartir su línea de crédito: el negocio pone su
  tarjeta en su cuenta de WhatsApp (Meta le cobra directo). Consecuencias: la pantalla de envío
  dice "Meta te cobra aprox. $X a tu tarjeta"; el tope de "envíos" del plan queda como freno
  anti-baneo, no como costo; revisar o quitar el paquete "+500 envíos" y los textos de planes.
  Los mensajes a quien escribió en las últimas 24 h son gratis.
- Contactos importados por coexistencia quedan "sin consentimiento confirmado": con plática
  cerrada (>24 h) NO se les reabre con plantilla (`_offer_or_queue`). Decidir si el dueño puede
  confirmarlos y cómo.

## Plan

### Fase 0 — Arreglos chicos que no esperan (≈ medio día)
1. `campaign_reach`: si el negocio no tiene WhatsApp conectado, `whatsapp = 0` y en su lugar un
   botón "Conecta el número de tu chip para llegarles por WhatsApp a N más". Hoy promete envíos
   que no salen.
2. `generate_campaign_variants`: pasarle productos y precios reales del catálogo (y lo relevante
   de la base de conocimiento) con la regla de no inventar; montos `$120`, no `$120.00`.

### Fase 1 — Campaña en 3 toques en la web (≈ 1–2 días)
1. "¿Qué quieres anunciar?" — un campo (y voz).
2. La IA arma mensaje (con catálogo real), sugiere cupón si aplica, pone nombre y tipo sola.
   Imagen o cuña solo si el plan del negocio las incluye.
3. Vista previa como la ve el cliente + alcance → "Mandar gratis por web" (principal),
   "Mandar también por WhatsApp ($X)" (solo si tiene WhatsApp conectado), "Cambiar".
- Lo actual (12 modos, A/B, secuencia, saga, plantillas) queda en "Más opciones", sin borrarse.
- Reutiliza: `POST /campaigns`, `/generate-content`, `/{id}/reach`, `/{id}/resume`.

### Fase 2 — Crear campaña desde el Copiloto (web y WhatsApp) (≈ 1 día)
- Herramienta nueva `create_campaign` (borrador) usando el mismo generador de la Fase 0/1, y
  `launch_campaign` ya existente con su confirmación (CONFIRM_TOOLS).
- Respuesta: vista previa + alcance + botones "Mandar" / "Cambiar" / "Cancelar".
- Por defecto "solo por web" si nadie del público tiene WhatsApp abierto o el negocio no tiene
  número propio.
- Conviene sacar la validación de `create_campaign` (REST) a `app/domain/campaign_actions.py`
  para que REST y Copiloto no se separen (lección de `6d27525`).

### Fase 3 — Que llegue y se mida (decidir después)
- Plantilla de reapertura automática: al conectar WhatsApp, crearla con `meta_templates` y
  guardarla en `meta_radio_invite_template_name`. Necesita revisar qué categoría acepta Meta
  (lección de `aviso_dueno`: la genérica la rechazan como Utilidad) — costo Marketing.
- Resultado simple por campaña: "La vieron N · Tocaron ¡La quiero! N · Cobraste a N" (este último
  sale de "Cobré" ligado al contacto en los días siguientes).
- NO mandar campañas de negocios por el número central (mezclaría marcas y gasta la reputación
  del número de IaRadio).

## Riesgos
- Dinero: Fases 2 y 3 tocan envíos que Meta cobra → `revisor-dinero` antes de subir.
- La IA puede proponer descuentos que el dueño no pidió: el cupón solo se sugiere, nunca se crea
  sin su "Sí".
- No hay datos de prod de cuántos negocios usan los modos avanzados (no se pudo medir sin tocar
  prod): por eso se esconden, no se quitan.

### Pruebas reales pendientes
- Campaña por WhatsApp desde un negocio con número conectado: (a) contacto con plática abierta
  (<24 h) → sale el mensaje directo; (b) contacto >24 h → sale la plantilla de reapertura.
  OJO: la web no deja escoger destinatarios, va a TODOS los contactos → usar una cuenta cuyo
  único contacto sea un teléfono del dueño.
- Añadir en Fase 1 "¿A quién?": todos / los que compraron / uno (para probar sin riesgo).

## Orden recomendado
Encender coexistencia (webhooks + prueba real CityCell) en paralelo con Fase 0 → Fase 1 →
Fase 2 → (decidir) Fase 3.
