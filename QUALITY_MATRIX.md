# Matriz de Calidad — IaRadio

> Actualizado 2026-07-31. La versión anterior (2026-06-04) predataba el retiro
> completo de Twilio y el sistema anti-baneo — varios números y filas de
> abajo cambiaron de forma sustancial, no solo cosmética.

---

## 🎯 Resumen Ejecutivo

| Indicador | Resultado |
|---|---:|
| Tests Backend (total) | 561 (548 previos + 13 nuevos de Team), 0 fallas conocidas (ver nota de `ALLOWED_HOSTS`/`REDIS_URL` locales) |
| Archivos de test backend | 49 |
| Tests Frontend | 124 ✅ |
| Archivos de test frontend | 21 |
| Routers backend sin ningún test dedicado | **4 de 24** (Admin, Public API, Appointments, Automations, Knowledge Base y Team cerrados 2026-07-31; User Webhooks también cerrado, no estaba contado en el 24 original) — ver tabla abajo |
| Capas del sistema anti-baneo | 10 (capas 6-15), todas en producción |

---

## 🖥️ Backend — API Endpoints

| Módulo | Tests dedicados | Notas |
|---|---|---|
| Campaigns | ✅ | Incluye recipient cap, segment cooldown, human-hour gate |
| Contacts | ⚠️ | Cubre pipeline y consentimiento CSV; falta CRUD básico |
| Conversations | ✅ | SSE, realtime, cambio de estado |
| Orders | ✅ | |
| Auth | ✅ | |
| Meta WhatsApp (`/me/whatsapp-*`) | ✅✅ | Conexión, salud de cuenta, warm-up, quality service — el módulo mejor cubierto del repo |
| Webhooks Meta | ✅✅ | Firma HMAC, quality updates, routing |
| Webhooks Stripe | ✅ | |
| Payments | ⚠️ | Solo vía webhook, sin tests directos de `payments.py` |
| Lab | ✅✅ | Endpoints, judge, personas, runner, simulator — muy completo |
| Appointments | ✅✅ | `test_appointments_endpoints.py` — CRUD con scoping por dueño, `/stats`, sync a Google Calendar (fallo tolerado sin bloquear creación), y `_sign_state`/`_verify_state` (firma HMAC del CSRF de OAuth) probados a fondo: firma alterada, user_id falsificado, token expirado. Sin bugs nuevos — `AppointmentOut` ya estaba bien tipado |
| User Webhooks | ✅✅ | `test_user_webhooks_endpoints.py` — CRUD + ping con `httpx` mockeado. Encontró y arregló un bug real: mismo patrón que Admin/Public API (`UserWebhookOut.created_at` tipado `str` recibiendo `datetime`), `POST`/`PATCH` tronaban siempre con 500 |
| Automations | ✅✅ | `test_automations_endpoints.py` — CRUD con scoping por dueño, whitelist de `trigger` (400), enrollment con 409 en duplicado y 404 cruzado (flujo/contacto de otro advertiser), cálculo de `next_send_at`. Sin bugs nuevos — `FlowOut`/`StepOut` ya estaban bien tipados |
| Knowledge Base | ✅✅ | `test_knowledge_base_endpoints.py` — list (scoping + filtro `is_active`, paginación), upload (gate de plan RAG, whitelist MIME, límite 50MB, dispatch a Celery mockeado), get-content (scoping), delete (scoping), `/test` bot (gate de plan, query vacía, respuesta mockeada de `answer_with_rag`). Sin bugs nuevos — este router devuelve dicts planos, no hay modelos Pydantic con el patrón `str`/`UUID`/`datetime` que sí rompió en Admin/Public API/User Webhooks |
| Team | ✅✅ | `test_team_endpoints.py` — invite (rol por default, whitelist agent/viewer, 409 en invitación duplicada, mismo email permitido entre dueños distintos), list (scoping, paginación), update-role (scoping, whitelist, 404), remove (scoping, 404). Sin bugs nuevos — `TeamMemberOut` ya estaba bien tipado (`id: UUID`, `invited_at`/`accepted_at: datetime`) |
| **Radio** | ❌ | |
| Public API | ✅✅ | `test_api_key_auth.py` (dependencia) + `test_public_api_endpoints.py` (handlers, DB real) — encontró y arregló un bug real: `POST /api/v1/api-keys` tronaba SIEMPRE con 500 (campo `created_at` tipado `str` recibiendo un `datetime`), nadie pudo haber creado una API key por HTTP hasta el fix |
| **Profile/Dash** | ❌ | |
| **Widget** | ❌ | |
| **Analytics** | ❌ | |
| Admin | ✅✅ | `test_admin_auth.py` (dependencia) + `test_admin_endpoints.py` (handlers, DB real) — encontró y arregló un bug real: `GET /admin/subscriptions/{id}/transactions` tronaba con 500 en cuanto el usuario tuviera una transacción (mismo tipo de bug: `TransactionResponse.id` sin el validador UUID→str que sus clases hermanas sí tenían) |

**Recomendación de orden si se sigue cerrando esta brecha:** el resto (Radio, Profile/Dash, Widget, Analytics) no tiene un orden crítico particular — todos son de prioridad similar (menor superficie de autorización/estado que lo ya cerrado).

---

## ⚙️ Backend — Servicios de mensajería / anti-baneo (nuevo desde la matriz anterior)

Todo lo relacionado a Meta WhatsApp reemplazó por completo a lo relacionado a
Twilio (fila "Twilio" de la matriz anterior — ya no existe el paquete `twilio`
en `requirements.txt`).

| Servicio | Qué hace | Tests |
|---|---|---|
| `meta_client.py` / `meta_service.py` | Cliente Graph API + envío de mensajes/plantillas/media | ✅✅ |
| `meta_connect_service.py` | Flujo de conexión "pegar credenciales → probar → guardar" | ✅ |
| `meta_quality_service.py` | Rating de calidad, warm-up, ban-risk error codes, next-human-hour | ✅✅ (capas 8/11/13/14 anti-baneo) |
| `crypto.py` | Cifrado AES-256-GCM de tokens en reposo | ✅ |
| `inbound_pipeline.py` | Bot, opt-out STOP, estado de pedidos/citas | ⚠️ handoff + opt-out cubiertos, resto parcial |
| `messaging_throttle.py` | Delay anti-baneo, gate de horario/domingo | ✅✅ |
| `task_helpers/campaign_ops.py` | Envío de campañas, tope de destinatarios, segment cooldown | ✅✅ |

## ⚙️ Backend — Otros servicios (sin cambios recientes, no re-verificados en esta pasada)

Claude, Embedding, RAG, Storage, Calendar, Banner, Radio (Scripts/TTS/Audio/Pipeline),
Imagen, Whisper, Coupon, Webhook Dispatcher, Demo Data — mantienen la cobertura
de la matriz de 2026-06-04 (no se tocaron en el trabajo de julio); re-verificar
conteos exactos antes de citarlos si ha pasado mucho tiempo.

---

## 🎨 Frontend — Páginas y Componentes

| Módulo | Tests | ErrorBound | Paginación | Print/PDF |
|---|---|---|---|---|
| CampaignsPage | ✅ | ⚠️ | ✅ | ✅ |
| ContactsPage | ✅ | ⚠️ | ✅ | ✅ |
| OrdersPage | ✅ | ⚠️ | ❌ | ✅ |
| SettingsPage | ✅ | ⚠️ | ◻️ | ◻️ |
| AppointmentsPage | ✅ | ⚠️ | ◻️ | ◻️ |
| KnowledgeBasePage | ✅ | ⚠️ | ◻️ | ◻️ |
| TeamPage | ✅ | ⚠️ | ◻️ | ◻️ |
| VerifyEmailPage | ✅ | ⚠️ | ◻️ | ◻️ |
| ResetPasswordPage | ❌ | ⚠️ | ◻️ | ◻️ |
| OnboardingWizard | ❌ | ⚠️ | ◻️ | ◻️ |
| WhatsappHealthCard | ✅ 8 | ◻️ | ◻️ | ◻️ |
| SEO | ✅ 6 | ◻️ | ◻️ | ◻️ |
| PrintButton | ✅ 4 | ◻️ | ◻️ | ✅ |
| CookieConsent | ✅ 4 | ◻️ | ◻️ | ◻️ |
| ErrorBoundary | ✅ 3 | ✅ | ◻️ | ◻️ |

**Sin tests aún**: PipelinePage, InboxPage (parcial vía `InboxPage.realtime.test.tsx`), LabPage, PlansPage, AutomationsPage, AnalyticsPage, WidgetPage, TemplatesPage, dashboard.

**Auditoría visual 2026-07-31**: se recorrieron las 16 vistas autenticadas en claro y oscuro con datos reales. Se encontraron y corrigieron: modo oscuro roto en ~50 inputs/selects (faltaba `bg-background text-foreground`), checkboxes con cuadro blanco fijo en dark mode (faltaba `color-scheme: dark` en `index.css` — el proyecto no usa `@tailwindcss/forms`), desalineación en TeamPage (`mx-auto` de más), overlap visual en WidgetPage, y espaciado irregular del eje X en AnalyticsPage (Recharts). Commit `70ca420`.

---

## 📋 Historial de Cambios

| Fecha | Cambio |
|---|---|
| 2026-07-31 | Cobertura de Automations (14 tests) — sin bugs nuevos (commit `eb9ea9b`) |
| 2026-07-31 | Confirmadas las 2 fallas de entorno local: `test_meta_incoming_webhook.py::TestPhoneNumberQualityUpdate` — `AllowedHostsMiddleware` rechaza el Host `test` que manda `httpx.AsyncClient(ASGITransport)` porque `.env` local trae `ALLOWED_HOSTS` sin `test`/`testserver` y `DEBUG=false`. No es bug de producción (los Hosts reales sí están permitidos); pendiente decidir si se agrega `testserver`/`test` al allowlist local o se ajusta el helper de estos tests |
| 2026-07-31 | Cobertura de Appointments (16 tests) — incluye la firma HMAC `_sign_state`/`_verify_state` del OAuth CSRF, sin cobertura previa; no se encontraron bugs nuevos (commit `cea2a8d`) |
| 2026-07-31 | Cobertura de User Webhooks (14 tests) — mismo bug de `str`/`datetime` que Admin/Public API encontrado y arreglado en `created_at` (commit `e279b56`) |
| 2026-07-31 | Cobertura de Admin + Public API (30 tests) — 2 bugs reales de 500 encontrados y arreglados en el proceso (commit `7ae199f`) |
| 2026-07-31 | Adaptador LLM OpenRouter/Anthropic intercambiable, activado y probado en vivo con modelo gratis (commits `17735a6`, `23af15f`) |
| 2026-07-31 | Escalado a humano pedido por el cliente + fix de falso positivo en detección de intención de plan (commits `eea99dd`, `b3370c3`) |
| 2026-07-31 | Auditoría visual completa (16 vistas, claro/oscuro) — bugs de dark mode, alineación y overlap corregidos (commit `70ca420`) |
| 2026-07-30/31 | Sistema anti-baneo completo, capas 6-15 (backend + frontend), ver `git log --grep="anti-baneo"` |
| 2026-07-30 | Retiro completo de Twilio consolidado; Meta Cloud API es el único canal |
| 2026-06-04 | **P14** — CampaignsPage paginación frontend + OrdersPage test |
| 2026-06-04 | **P12-P13** — Idempotencia real: store_idempotency_response en 8 endpoints + Widget |
| 2026-06-04 | **P2-P3** — N+1 verificado sin issues (todos ✅) |
| 2026-06-04 | **P13** — Parrilla con PrintButton interno, encabezado print-only, print-keep-together |
| 2026-06-04 | **P12** — Fix truncado PDF: h-screen/overflow-hidden liberados en @media print |
| 2026-06-04 | **P10** — 128 tests unitarios para 15 servicios backend |
| 2026-06-04 | **P6** — Return types en 105 endpoints de 20+ route files |
| 2026-06-04 | **P1-P9** — Rate-limit, N+1, async, paginación, idempotencia, types, logs, tests |
| 2026-06-04 | **P11** — 96 tests frontend para 14 módulos |
| 2026-06-04 | Matriz inicial |

---

## 🏁 Leyenda

| Símbolo | Significado |
|---|---|
| ✅ | Completado / Sin issues |
| ⚠️ | Parcial / En progreso |
| ❌ | No implementado |
| ◻️ | No aplica |
