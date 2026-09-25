# Plan de Lanzamiento — IaRadio

## Estado actual (17 sep 2026)

La plataforma **ya está en producción** en `www.iaradio.online` (Railway), no es un
lanzamiento desde cero — este documento es el plan para el primer lote de
clientes reales con WhatsApp conectado manualmente.

### Verificado en esta auditoría
- Producción viva: `web`, `worker`, `beat` y Redis — los 4 servicios de Railway
  `RUNNING` en el commit `2aa1b65` (el HEAD actual de `master`). `GET /health` → 200.
- Sistema anti-baneo de WhatsApp en capa **17** (consentimiento, quality rating
  en tiempo real + polling, throttle adaptativo, cooldown de segmento, warm-up,
  opt-out, auto-pausa por error codes, opt-in de ventana cerrada en las 4 rutas
  de envío).
- Twilio fue retirado por completo — el único canal es **Meta Cloud API directa**,
  cada anunciante con su propio WABA (nada de número compartido ni pool).
- Stripe en modo live, Sentry configurado, backup diario de BD (pg_dump →
  GitHub Actions) corriendo sin fallas.
- `META_APP_ID`, `META_APP_SECRET` y `META_EMBEDDED_SIGNUP_CONFIG_ID` ya están
  cargados en Railway (en agosto `META_APP_SECRET` seguía vacío — ya no).

### ⚠️ Hallazgo importante: Embedded Signup sigue apagado
El botón "Conectar con Meta" (OAuth de un clic) **no se muestra en producción**
todavía: además de las tres variables de arriba, requiere el interruptor
explícito `META_EMBEDDED_SIGNUP_ENABLED=true` en Railway, y hoy **no está
seteado** (default `False` en `app/config.py`). Está así a propósito hasta que
Meta apruebe la verificación de negocio y el App Review de acceso avanzado —
ver el comentario en `WhatsappWizard.tsx`.

**Consecuencia práctica: la única vía real para conectar un WABA hoy es el
formulario manual.** El plan de abajo asume eso — no depende de que Meta
apruebe nada para arrancar con los primeros clientes.

### Gaps de calidad detectados en esta auditoría (no bloquean producción, pero hay que cerrarlos pronto)
- **CI de backend lleva roto ~50 pushes seguidos** (desde el 10 de agosto):
  el step de `ruff` corre antes que `pytest` y aborta el job — la suite real
  de tests **no se ha ejecutado en CI en más de un mes**. `master` no tiene
  branch protection, por eso nunca bloqueó nada. Hay 881 errores de lint
  acumulados (389 auto-arreglables con `ruff check --fix`).
- Corriendo la suite localmente contra Postgres+Redis reales (1003 tests) se
  encontró al menos 1 falla real: `tests/test_api.py::test_customer_stories_public`
  (pendiente de diagnosticar — ver seguimiento).
- Sigue sin haber monitoreo de uptime externo (Better Uptime o equivalente) —
  pendiente desde julio.

---

## Plan de conexión manual del WABA (la vía real hoy)

Esto es lo que cada anunciante hace en `Configuración → WhatsApp` (componente
`WhatsappWizard.tsx`, ya en producción). Documentado aquí para poder guiar a
un cliente por teléfono/presencial sin improvisar:

1. **Cuenta de negocio + WABA**: el cliente entra a
   [business.facebook.com](https://business.facebook.com) con su cuenta
   personal → crea/entra a su Business Manager → barra lateral → **WhatsApp**
   → **Empezar a usar**. Esto crea su WhatsApp Business Account (WABA) gratis.
   El WABA ID se ve directo en `business.facebook.com/settings/whatsapp-business-accounts`.
2. **Número de teléfono**: dentro de la WABA → **Configuración de números de
   teléfono** → **Agregar número**. Debe ser un número **libre de WhatsApp**
   (otro chip, no el personal). Se verifica con el código SMS/llamada que le
   llega a ese número.
3. **App en Meta for Developers**: en developers.facebook.com/apps → **Crear
   app** (tipo "Negocio") → agregar producto **WhatsApp**. Ahí aparecen
   **WABA ID** y **Phone Number ID** (sección "API Setup"), y **App ID** /
   **App Secret** en "Configuración de la app → Básico".
4. **Token permanente**: `business.facebook.com/settings/system-users` →
   crear usuario del sistema con esa app → permisos
   `whatsapp_business_messaging` + `whatsapp_business_management` → **Generar
   token** (sin expiración). Ese token de larga duración es el que se pega en
   el formulario.
5. **Pegar y probar**: WABA ID + Phone Number ID + token en el wizard →
   "Probar conexión" (valida contra Graph API sin guardar nada) → "Guardar".
   Si además pega su propio App ID + App Secret, el backend
   (`meta_connect_service.subscribe_app_to_waba` + `configure_app_webhook`)
   deja el webhook de esa app apuntando a
   `https://www.iaradio.online/api/v1/webhooks/meta` automáticamente — sin
   eso, el cliente no recibe las respuestas entrantes de sus contactos.
6. **Plantillas aprobadas**: pegar el nombre de al menos una plantilla ya
   aprobada en WhatsApp Manager (cualquier categoría) para reapertura de
   ventana de 24h y recordatorios de citas — sin esto esos mensajes degradan
   a texto plano fuera de ventana.

**Checklist operativo para onboarding presencial/telefónico (10-15 min):**
- [ ] Confirmar que el cliente tiene un chip libre de WhatsApp a la mano
- [ ] Acompañarlo en los pasos 1-4 por videollamada o presencial
- [ ] Verificar juntos que "Probar conexión" da ✓ antes de guardar
- [ ] Confirmar `webhook_configured: true` en el estado de la conexión
      (si pegó su propia App ID/Secret) — si no, revisar App Secret
- [ ] Pedirle al menos 1 plantilla aprobada o ayudarlo a crear una en
      WhatsApp Manager
- [ ] Enviar un mensaje de prueba real y confirmar que el bot responde

---

## Semana 1: Dogfooding y primeros WABAs reales (días 1-3)

- [ ] Conectar el WABA propio de IaRadio (si no está ya) siguiendo el flujo
      manual de arriba, de punta a punta, para detectar fricción real
- [ ] Subir base de conocimiento (FAQ) y probar el bot con preguntas reales
- [ ] Crear una campaña y enviarla a un contacto de prueba, confirmar
      cooldown/consentimiento/opt-out funcionando (capas anti-baneo)
- [ ] Verificar panel admin con datos reales de esa cuenta

## Semana 2: Primeros clientes (días 4-10)

- [ ] Retomar la base de negocios de Tlaxiaco (CSV con 104 negocios,
      `contactos_tlaxiaco.csv`) — confirmar que sigue vigente el consentimiento
      (capa 6: contactos CSV entran como `unconfirmed` hasta que respondan)
- [ ] Onboarding presencial: acompañar la conexión manual del WABA
      (checklist de arriba), primer mes gratis → recurrente
- [ ] Seguimiento a leads sin responder, feedback de los primeros usuarios

---

## Antes de escalar más allá del primer lote (bloqueadores de proceso, no de producto)
- [ ] Arreglar el gate de CI: correr `ruff check --fix` para los 389 fixables,
      revisar a mano el resto, y volver a poner `pytest` a correr en cada push
- [ ] Diagnosticar y arreglar `test_customer_stories_public`
- [ ] Activar branch protection en `master` exigiendo CI verde antes de merge
- [ ] Contratar monitoreo de uptime externo (Better Uptime o equivalente)
- [ ] Cuando Meta apruebe verificación de negocio: activar
      `META_EMBEDDED_SIGNUP_ENABLED=true` para ofrecer el OAuth de un clic
      junto al formulario manual (no en reemplazo — dejar ambos)

---

## Costos estimados (mensual, régimen actual)

| Servicio | Costo |
|----------|-------|
| Meta Cloud API (mensajes) | Gratis hasta cierto volumen / plantillas de pago según categoría |
| Stripe fee | 2.9% + $0.30 USD por transacción |
| Railway (web + worker + beat + Redis) | ~$15-20 USD/mes según uso |
| Neon Postgres | Free tier / escalable |
| **Total aprox. primer mes** | **~$20-30 USD** |

---

## Estrategia futura
- Nicho Oaxaca (venta directa a negocios locales)
- Agencias de marketing (white-label)
- Trueque con radios comunitarias
