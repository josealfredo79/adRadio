# Plan de Lanzamiento — IaRadio

## Estado actual (12 oct 2026)

Producción viva en `www.iaradio.online` (Railway: web, worker, beat, Redis), último
commit verificado `2fc0ade`. **Decisión:** lanzamiento **suave** con 5–10 negocios
de Tlaxiaco, no lanzamiento abierto. La web es el camino principal (avisos gratis,
sin baneo); WhatsApp es el anzuelo.

### Listo
- Producto: bot con IA (cadena gratis → Claude), página del negocio, tarjeta del
  cliente (/c/), avisos web, citas, pedidos, lealtad, campañas, Inbox (aprende de
  las respuestas del dueño), Copiloto, configuración por voz.
- Meta: App Review **aprobada** (11-oct) y app **publicada**. "Conectar con Meta"
  en v4, encendido solo para admins + cuentas de prueba (`META_EMBEDDED_SIGNUP_TEST_EMAILS`).
  Coexistencia (mismo número de la app WhatsApp Business) construida.
- Cobro: Stripe **en vivo**, cuenta MX lista para cobrar y depositar, webhook activo,
  **cobra en pesos** el precio anunciado (desde `d90e7a8`).
- Voz: si Microsoft bloquea edge-tts (pasa desde ~10-oct), cae sola a Google.
- Calidad: 1,596 pruebas con BD y Redis reales; monitoreo cada 10 min
  (`/health/ready`, abre issue "caída"); respaldo diario de la BD; Sentry en el servidor.
- Legales: /terms, /privacy y /data-deletion en línea.
- Variables de Railway revisadas (12-oct): no falta ninguna crítica.

## 🔴 Bloqueadores (antes del primer negocio que paga)

| # | Qué | Quién | Tiempo |
|---|-----|-------|--------|
| 1 | ✅ **Cobro** probado 13-oct: $449,00 MXN, plan activo, cancelar y reembolso OK. La prueba destapó que el webhook tronaba en todo pago real y que las renovaciones no se acreditaban — arreglado (`fc5e5bb`) | — | Hecho |
| 2 | ✅ **Campañas por web** probadas 13-oct: promo y cuña llegan al chat con cupón, audio y "¡La quiero!" (`dfb7f2a`…`825e8a7`). Falta ver que la notificación de Chrome suene (revisar `chrome://gcm-internals`) | Dueño + Claude | 10 min |
| 3 | **Neon — URGENTE**: el 13-oct iba en 80/100 horas de cómputo; beat y el monitoreo no dejan dormir la base y al 100% (~16-oct) producción cae. Pasar a Launch Plan | Dueño | 5 min (~US$19/mes) |
| 4 | **Voyage**: poner tarjeta (hoy 3 búsquedas/min en total; los 200M tokens gratis siguen) | Dueño | 2 min |

### Prueba de campañas por web
Chrome normal (no incógnito). Pestaña A = panel CityCell (dueño), B = tarjeta de cliente.
1. A: Configuración → "Agente inteligente" → **Probar como cliente** (abre B).
2. B: **Activar avisos**.
3. A: Campañas → promoción `Hola {{nombre}}, 2x1 en fundas esta semana en {{negocio}} 📱`,
   etiqueta **prueba**, enviar **Solo por web**.
4. Llega la notificación → abre la promo → "¡La quiero!" abre el chat con esa promo.
5. A: la campaña marca 1 enviada y 1 leída. (Ya probado de punta a punta en local:
   `tests/test_campaign_web_e2e.py`.)

## 🟡 Variables para el lanzamiento

| Variable | Para qué | Cuándo |
|---|---|---|
| `POSTHOG_API_KEY` (web y worker) | Medir registros, prueba→pago, checkouts sin pagar — hoy no se mide nada | **Antes del piloto** |
| `VITE_SENTRY_DSN` | Errores del navegador del cliente | Primeras semanas |
| `META_EMBEDDED_SIGNUP_ADMINS_ONLY=false` | Abrir "Conectar con Meta" a todos | Tras la prueba real con un número |

Las llaves se pasan con `!` en la terminal, nunca pegadas en el chat.

## 🟡 Importante, no frena el piloto
- CI de GitHub en rojo desde el 9-oct por reglas de estilo de `ruff` (no por fallas);
  hay un cambio local sin subir en `ci.yml` del dueño. Luego: branch protection.
- "Conexión a la BD cerrada" (12 en 3 h el 12-oct): revisar junto con el plan de Neon.
- Rotar la contraseña de `iaradio@iaradio.online` (salió en una captura).
- Migrar `railway.json` (Config as Code) antes del **1-dic-2026**.
- Prueba real de coexistencia: suscribir en Meta `history`, `smb_app_state_sync`,
  `smb_message_echoes`, `account_update` y conectar un número con la app WhatsApp Business.
- Catálogo de la cuenta IaRadio: quitar los planes viejos (Starter/Growth/Pro/Business).
- Turnstile (captcha invisible) no está construido; por ahora trampas y topes.

## Plan del lanzamiento suave
1. **Día 1:** cerrar los 4 bloqueadores y poner PostHog.
2. **Días 2–3:** dar de alta en persona 5–10 negocios de Tlaxiaco (CSV de 104
   negocios); gancho: precio **Fundadores** ($319 / $629, cupo limitado).
3. **Semanas 1–2:** `/salud-bot` y `/revisar-prod` a diario; recoger lo que dicen los dueños.
4. **Con 3+ negocios pagando y contentos:** abrir "Conectar con Meta" a todos y
   arrancar el piloto de **Promotores** (25% recurrente 12 meses; consultar contador antes).

### Métricas del piloto
- Altas por semana, % prueba → pago, % que sigue pagando al 2º mes.
- % de clientes de cada negocio que activan avisos web (que "estén ahí").

## IaRadio que se arregla solo
Ya se recupera solo de:
- Un modelo de IA caído → pasa al siguiente de la cadena.
- Voz de Microsoft bloqueada → Google, y reintenta a los 10 min.
- Búsqueda (Voyage) saturada → contesta sin buscar en vez de colgarse.
- Aviso de Meta perdido en el navegador → el servidor revisa `is_on_biz_app`.
- Sitio caído → el monitoreo abre un issue en GitHub.

Siguiente paso (idea, no construida): un chequeo diario automático (`salud-bot`
programado) que lea los registros de producción, detecte lo conocido (modelos que
dejan de existir, 429 de Voyage, conexiones de BD cerradas, errores nuevos) y
**abra el arreglo** o avise al dueño antes de que lo note un cliente.

## Costos mensuales aproximados
| Servicio | Costo |
|---|---|
| Railway (web, worker, beat, Redis) | ~US$15–20 |
| Neon Postgres (plan de pago recomendado) | ~US$19 |
| Stripe | ~3.6% + comisión fija por cobro (tarifa México) |
| Google TTS (respaldo de voz) | 1M caracteres gratis/mes |
| Voyage (búsqueda) | 200M tokens gratis, luego por uso |
| Meta (WhatsApp) | Lo paga cada negocio en su cuenta |
