<div align="center">

# IaRadio

**Radio Publicitaria Inteligente por WhatsApp**

Plataforma SaaS que permite a cualquier negocio crear, enviar y medir campañas de audio publicitarias por WhatsApp — con IA generativa, base de conocimiento propia y atención automatizada 24/7.

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+pgvector-4169E1?logo=postgresql&logoColor=white)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

## Qué hace IaRadio

| Característica | Descripción |
|---|---|
| 🎙️ **Parrilla Semanal (IA)** | Generación automática de 7 días de contenido radial (Cápsulas, Trivias, Estacional) |
| 📢 **Campañas masivas** | Envío asíncrono con Celery y Redis, respetando delays anti-ban |
| 📅 **Gestión de Citas** | Webhooks para confirmación ("1") y rescate inteligente/reagendamiento ("2" -> "Sí") |
| 🤖 **Bot conversacional** | Responde preguntas de clientes usando RAG sobre la base de conocimiento del negocio |
| 📊 **Analytics en tiempo real** | KPIs de entrega, apertura y respuesta cacheados en Redis |
| 🛒 **Gestión de pedidos** | Estado de pedidos vía WhatsApp con flujo automatizado de 4 pasos |
| 💳 **Suscripciones Stripe** | Planes Starter → Growth → Pro+ con validación estricta de cuotas |
| 📋 **Base de conocimiento** | Sube PDFs, Word o texto plano → embeddings Voyage AI → búsqueda semántica |

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                     Railway / Docker                    │
│                                                         │
│  ┌───────────────┐   ┌─────────────┐  ┌─────────────┐  │
│  │ FastAPI :8000 │   │Celery Worker│  │ Celery Beat │  │
│  │  + React SPA  │   │(tasks async)│  │ (scheduled) │  │
│  └──────┬────────┘   └──────┬──────┘  └──────┬──────┘  │
│         │                   │                │          │
│  ┌──────▼───────────────────▼────────────────▼──────┐   │
│  │              Redis  (cache + broker)             │   │
│  └──────────────────────────┬───────────────────────┘   │
│                             │                           │
│  ┌──────────────────────────▼───────────────────────┐   │
│  │         Neon PostgreSQL 16 + pgvector            │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
         │                              │
    Twilio WhatsApp              Cloudflare R2
    (envío/recepción)            (audio, archivos)
```

**Servicios externos:** Anthropic Claude · Voyage AI · Fish Audio · Stripe · Twilio · Cloudflare R2 · Neon · Sentry

---

## Estructura del proyecto

```
iaradio/
├── Dockerfile                  # Multi-stage: Node 20 build → Python 3.12 serve
├── docker-entrypoint.sh        # Detecta SERVICE_ROLE (api / worker / beat)
├── docker-compose.yml          # Stack local completo
├── railway.toml                # Configuración Railway
│
├── backend/
│   ├── app/
│   │   ├── api/v1/             # Routers REST (auth, contacts, campaigns…)
│   │   ├── core/               # JWT, email, Redis
│   │   ├── models/             # SQLAlchemy ORM (User, Contact, Campaign…)
│   │   ├── schemas/            # Pydantic v2 schemas
│   │   ├── services/           # Claude, RAG, Twilio, Stripe, R2, TTS
│   │   ├── workers/            # Celery app + tasks
│   │   └── main.py             # FastAPI entry point + SPA catch-all
│   ├── alembic/                # Migraciones de BD
│   ├── requirements.txt
│   └── .env.example
│
└── frontend/
    └── src/
        ├── pages/              # Dashboard, Campañas, Contactos, Inbox, Pedidos…
        ├── components/         # Layout (mobile-responsive + nav badges)
        ├── contexts/           # AuthContext (JWT en memoria, XSS-safe)
        └── lib/                # Axios client con auto-refresh token
```

---

## Inicio rápido (desarrollo local)

### Requisitos
- Docker Desktop ≥ 24

### 1. Clonar y configurar

```bash
git clone https://github.com/tu-usuario/iaradio.git
cd iaradio
cp backend/.env.example backend/.env
# Editar backend/.env con tus API keys
```

### 2. Levantar el stack

```bash
docker compose up --build
```

| Servicio | URL |
|---|---|
| Frontend (React) | http://localhost:5173 |
| API | http://localhost:8000 |
| Docs API | http://localhost:8000/docs |

### 3. Primera vez — ejecutar migraciones

```bash
docker compose exec backend alembic upgrade head
```

---

## Variables de entorno

Ver [`backend/.env.example`](backend/.env.example) para la lista completa.

### Mínimas para desarrollo

```env
DATABASE_URL=postgresql+asyncpg://iaradio:iaradio_dev@localhost/iaradio
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=<openssl rand -hex 32>
ANTHROPIC_API_KEY=sk-ant-...
VOYAGE_API_KEY=pa-...
```

### Requeridas en producción

```env
# Auth & App
SECRET_KEY=                       # openssl rand -hex 32
FRONTEND_URL=https://<dominio>.up.railway.app   # para CORS dinámico

# Base de datos
DATABASE_URL=postgresql+asyncpg://...neon.tech/iaradio?ssl=require

# Cache / broker
REDIS_URL=redis://...railway.internal:6379

# WhatsApp
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_NUMBER=+14155238886

# Pagos
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PUBLISHABLE_KEY=

# IA
ANTHROPIC_API_KEY=
VOYAGE_API_KEY=
FISH_AUDIO_API_KEY=

# Almacenamiento (Cloudflare R2)
CF_R2_ACCESS_KEY=
CF_R2_SECRET_KEY=
CF_R2_BUCKET=iaradio-files
CF_R2_ENDPOINT=https://<account>.r2.cloudflarestorage.com
CF_R2_PUBLIC_URL=https://files.iaradio.app

# Email
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USER=resend
SMTP_PASSWORD=re_...
FROM_EMAIL=hola@iaradio.app
```

---

## Deploy en Railway

### 1 — Sube el código

```bash
git add -A && git commit -m "feat: production-ready" && git push
```

### 2 — Crea el proyecto

[railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo** → selecciona el repo.

### 3 — Agrega servicios

| Servicio | Cómo crearlo | Variable clave |
|---|---|---|
| **Redis** | New Service → Redis (template Railway) | — |
| **Worker** | New Service → Same Repo | `SERVICE_ROLE=worker` |
| **Beat** | New Service → Same Repo | `SERVICE_ROLE=beat` |

### 4 — Variables de entorno

Pega el bloque de producción en el servicio principal (`api`).

### 5 — Deploy

Railway ejecuta automáticamente:
1. `npm run build` (Node 20) → construye la SPA
2. `pip install` (Python 3.12) → instala dependencias
3. `alembic upgrade head` → aplica migraciones
4. `uvicorn app.main:app` → levanta API + SPA en un solo contenedor

---

## API — Endpoints principales

| Método | Endpoint | Descripción |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Registro + verificación email |
| `POST` | `/api/v1/auth/login` | Login → JWT tokens |
| `POST` | `/api/v1/auth/refresh` | Renueva access token con httpOnly cookie |
| `GET` | `/api/v1/dashboard` | KPIs cacheados en Redis |
| `GET/POST` | `/api/v1/contacts` | CRUD contactos |
| `POST` | `/api/v1/contacts/import-csv` | Importación masiva asíncrona |
| `GET` | `/api/v1/contacts/export-csv` | Exportar contactos a CSV |
| `GET/POST` | `/api/v1/campaigns` | CRUD campañas |
| `POST` | `/api/v1/campaigns/generate-content` | Claude genera 3 variantes de guión |
| `POST` | `/api/v1/campaigns/{id}/send` | Envío masivo vía Celery |
| `GET` | `/api/v1/conversations` | Inbox WhatsApp paginado |
| `POST` | `/api/v1/conversations/{id}/reply` | Responder desde el inbox |
| `POST` | `/api/v1/knowledge-base/upload` | Sube archivo → embeddings automáticos |
| `POST` | `/api/v1/radio/generate` | Genera cuña de radio con audio |
| `GET/PATCH` | `/api/v1/orders` | Gestión de pedidos WhatsApp |
| `POST` | `/api/v1/webhooks/twilio` | Webhook WhatsApp entrante (firma validada) |
| `POST` | `/api/v1/webhooks/stripe` | Webhook pagos Stripe (firma validada) |
| `GET` | `/health` | Health check |

---

## Seguridad

- **Autenticación:** JWT access token (1 h, en memoria) + refresh token httpOnly cookie (7 d) con rotación
- **Contraseñas:** bcrypt factor 12
- **Rate limiting:** 200 req/min por IP
- **Webhooks:** validación de firma `X-Twilio-Signature` y `Stripe-Signature`
- **Uploads:** validación MIME real, máx. 20 MB
- **CORS:** whitelist explícita, ampliable con `FRONTEND_URL`
- **Email:** verificación obligatoria antes del primer login
- **Opt-out:** auto-unsubscribe en palabras STOP / BAJA / CANCELAR

---

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | React 18, TypeScript, Vite 6, TailwindCSS, TanStack Query v5, Radix UI |
| Backend | FastAPI 0.115, Python 3.12, SQLAlchemy 2 async, Pydantic v2 |
| Base de datos | Neon PostgreSQL 16 + pgvector (embeddings 1024d) |
| Cache / Broker | Redis 7 |
| Workers | Celery 5 |
| IA | Claude 3.5 Sonnet, Voyage AI, Fish Audio TTS |
| WhatsApp | Twilio WhatsApp Business API |
| Pagos | Stripe Checkout + Webhooks |
| Almacenamiento | Cloudflare R2 (S3-compatible) |
| Monitoreo | Sentry, PostHog |
| Deploy | Railway (Docker multi-stage, un contenedor por servicio) |

---

## Licencia

MIT © 2026 IaRadio. Hecho con ❤️ en México.
