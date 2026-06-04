# Matriz de Calidad — IaRadio

## 📊 Resumen general

| Categoría | Salud |
|-----------|-------|
| **Backend — Tests (`tests/`)** | ✅ 146 tests (9 files) |
| **Backend — Tests servicios** | ✅ 128 tests |
| **Backend — Tests integración** | ⚠️ 7 archivos sueltos (DB, Twilio, Redis, etc.) |
| **Frontend — Tests** | ✅ 96 tests (16 archivos, 14 módulos) |
| **Frontend — Componentes** | ✅ 4 componentes con tests |
| **Frontend — Pages** | ✅ 10 pages con tests |
| **PDF / Print** | ✅ 3 páginas (Orders, Campaigns, Contacts) |
| **Parrilla de contenido** | ✅ Generación + impresión PDF |

---

## Backend — Módulos API (solo dimensiones con ❌ o ⚠️)

| Módulo | Tests | Logs | Idempot | N+1 |
|--------|:-----:|:----:|:-------:|:---:|
| Campaigns | ✅ | ✅ | ❌ | ⚠️ |
| Contacts | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| Appointments | ❌ | ✅ | ⚠️ | ◻️ |
| Payments | ❌ | ⚠️ | ⚠️ | ◻️ |
| Knowledge Base | ❌ | ⚠️ | ❌ | ◻️ |
| Automations | ❌ | ⚠️ | ⚠️ | ✅ |
| Team | ❌ | ⚠️ | ⚠️ | ◻️ |
| Conversations | ❌ | ⚠️ | ⚠️ | ⚠️ |
| Radio | ❌ | ✅ | ◻️ | ◻️ |
| Public API | ❌ | ⚠️ | ❌ | ◻️ |
| Profile/Dash | ❌ | ⚠️ | ❌ | ◻️ |
| Widget | ❌ | ✅ | ❌ | ◻️ |
| Analytics | ❌ | ✅ | ◻️ | ◻️ |

Todos los demás campos (Auth, Validación, Paginación, SQL Inj, Async, Types) están ✅.

## Backend — Servicios

| Servicio | Tests | Types | Logs |
|----------|:-----:|:-----:|:----:|
| Claude | ✅ (11) | ⚠️ | ⚠️ |
| Embedding | ✅ (8) | ⚠️ | ⚠️ |
| RAG | ✅ (4) | ⚠️ | ⚠️ |
| Storage | ✅ (4) | ⚠️ | ⚠️ |
| Calendar | ✅ (6) | ⚠️ | ⚠️ |
| Banner | ✅ (6) | ⚠️ | ⚠️ |
| Number Pool | ✅ (8) | ⚠️ | ⚠️ |
| Radio Scripts | ✅ (5) | ⚠️ | ⚠️ |
| Radio TTS | ✅ (3) | ⚠️ | ⚠️ |
| Radio Audio | ✅ (7) | ⚠️ | ⚠️ |
| Radio Pipeline | ✅ (2) | ⚠️ | ⚠️ |
| Imagen | ✅ (6) | ⚠️ | ⚠️ |
| Whisper | ✅ (4) | ⚠️ | ⚠️ |
| Coupon | ✅ (8) | ⚠️ | ⚠️ |
| Twilio | ✅ (1) | ⚠️ | ⚠️ |
| Webhook Dispatcher | ✅ (2) | ⚠️ | ⚠️ |
| Demo Data | ✅ (1) | ⚠️ | ⚠️ |

## Frontend — Módulos

| Módulo | Tests | ErrorBound | Paginación | Print/PDF |
|--------|:-----:|:----------:|:----------:|:---------:|
| CampaignsPage | ✅ | ⚠️ | ❌ | ✅ |
| ContactsPage | ✅ | ⚠️ | ✅ | ✅ |
| OrdersPage | ❌ | ⚠️ | ❌ | ✅ |
| SettingsPage | ✅ | ⚠️ | ◻️ | ◻️ |
| AppointmentsPage | ✅ | ⚠️ | ◻️ | ◻️ |
| KnowledgeBasePage | ✅ | ⚠️ | ◻️ | ◻️ |
| TeamPage | ✅ | ⚠️ | ◻️ | ◻️ |
| VerifyEmailPage | ✅ | ⚠️ | ◻️ | ◻️ |
| ResetPasswordPage | ❌ | ⚠️ | ◻️ | ◻️ |
| OnboardingWizard | ❌ | ⚠️ | ◻️ | ◻️ |
| SEO | ✅ (6) | ◻️ | ◻️ | ◻️ |
| PrintButton | ✅ (4) | ◻️ | ◻️ | ✅ |
| CookieConsent | ✅ (4) | ◻️ | ◻️ | ◻️ |
| ErrorBoundary | ✅ (3) | ✅ | ◻️ | ◻️ |

---

## 🏴 Prioridades

| # | Área | Estado |
|---|------|:------:|
| P1 | Radio endpoint — sin auth | ✅ |
| P2 | N+1 en Orders | ✅ |
| P3 | Radio boto3 bloqueante | ✅ |
| P4 | Paginación (5 módulos) | ✅ |
| P5 | Idempotencia en POST | ✅ |
| P6 | Return types en 105 endpoints | ✅ |
| P7 | Logging (widget, analytics, radio) | ✅ |
| P8 | Tests funcionales backend | ✅ |
| P9 | Tests frontend iniciales | ✅ |
| P10 | 128 tests servicios backend | ✅ |
| P11 | 96 tests frontend (14 módulos) | ✅ |
| P12 | Print/PDF en Orders, Campaigns, Contacts | ✅ |
| P13 | Parrilla de contenido con impresión | ✅ |

---

## Historial de cambios

| Fecha | Cambio |
|-------|--------|
| 2026-06-04 | P13: Parrilla con PrintButton interno, encabezado print-only, print-keep-together |
| 2026-06-04 | P12: Fix truncado PDF — liberar h-screen/overflow-hidden en @media print |
| 2026-06-04 | P10: 128 tests unitarios para 15 servicios backend |
| 2026-06-04 | P6: return types en 105 endpoints de 20+ route files |
| 2026-06-04 | P1-P9 completados (rate-limit, N+1, async, paginación, idempotencia, types, logs, tests) |
| 2026-06-04 | P11: 96 tests frontend para 14 módulos |
| 2026-06-04 | Matriz inicial |
