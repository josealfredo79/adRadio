# IaRadio — Copilot Instructions

## Proyecto
**IaRadio / adRadio v2.0.0** — SaaS de marketing por WhatsApp para anunciantes de radio.
- Campañas masivas vía Twilio WhatsApp API con anti-ban delays
- Bot con IA (Claude Anthropic) + RAG (VoyageAI + pgvector)
- Generación de cuñas de radio con TTS (Fish Audio, Google TTS, Edge TTS)
- Pagos con Stripe, almacenamiento en Cloudflare R2
- Monitoreo con Sentry + PostHog
- Despliegue: Docker Compose (dev) + Railway (prod)

## Stack completo

### Backend (`backend/`)
- **Framework**: FastAPI 0.115 + Uvicorn (async/await)
- **DB**: PostgreSQL 16 + pgvector, SQLAlchemy 2.0 async (`asyncpg`)
- **Migraciones**: Alembic (`backend/alembic/versions/`)
- **Cache/Broker**: Redis 7
- **Tareas async**: Celery 5.4 + Beat scheduler
- **Auth**: JWT con python-jose (access 60 min, refresh 7 días)
- **Rate limiting**: SlowAPI (Redis, fallback memory) — 200 req/min global
- **Config**: pydantic-settings via `.env`
- **Entrypoint**: `backend/app/main.py`
- **Venv**: `backend/.venv/`

### Frontend (`frontend/`)
- **Framework**: React 18 + TypeScript + Vite 6
- **Estilos**: TailwindCSS 3 + shadcn/ui (Radix UI primitives)
- **Estado servidor**: TanStack React Query v5
- **Forms**: react-hook-form + Zod
- **Routing**: React Router DOM v7
- **Gráficos**: Recharts
- **Tests**: Vitest + Testing Library + Playwright (e2e)

## Estructura de carpetas clave

```
backend/app/
├── api/v1/          # Endpoints REST (un archivo por dominio)
├── models/          # SQLAlchemy ORM models
├── schemas/         # Pydantic schemas (request/response)
├── services/        # Lógica de negocio
│   ├── claude_service.py      # Anthropic Claude AI
│   ├── rag_service.py         # RAG con pgvector
│   ├── embedding_service.py   # VoyageAI embeddings
│   ├── twilio_service.py      # WhatsApp via Twilio
│   ├── radio_service.py       # Generación cuñas radio (27KB)
│   ├── storage_service.py     # Cloudflare R2 (S3 compat)
│   └── calendar_service.py    # Google Calendar
├── workers/tasks.py # Celery tasks (34KB) — campañas async
├── core/            # Redis, auth helpers, rate_limiter
├── config.py        # Settings con pydantic-settings
├── database.py      # SQLAlchemy async engine
└── main.py          # Entry point, middlewares, routers

frontend/src/
├── pages/           # Una página por funcionalidad (lazy-loaded)
├── components/      # Componentes reutilizables
├── contexts/        # AuthContext
└── lib/             # Utilidades, axios instance
```

## Modelos de BD (19 core)
`User`, `Contact`, `Campaign`, `Message`, `Conversation`, `KnowledgeBase`,
`Transaction`, `ProspectsPool`, `Coupon`, `Order`, `Appointment`, `APIKey`,
`Automation`, `MessageTemplate`, `CustomerStory`, `TeamMember`, `UserWebhook`, `TemplateSeeds`

`User.role`: `admin` | `advertiser`
`User.plan_status`: `trial` | `active` | `suspended` | `churned`
`User.whatsapp_subscription`: `shared` | `pool` | `own`

## Convenciones de código

### Python/Backend
- Siempre usar `async/await` — NO código sincrónico bloqueante en endpoints
- Dependency injection vía `Depends()` para DB session, usuario actual
- DB session: `AsyncSession` de `database.py` → `get_db()` dependency
- Nunca usar `session.execute(text(...))` sin parámetros vinculados (SQL injection)
- Schemas Pydantic separados para Request y Response
- Errores HTTP: usar `HTTPException` con códigos semánticos

### TypeScript/React
- Componentes funcionales con hooks únicamente
- TanStack Query para todo estado del servidor (NO `useEffect` + `fetch`)
- Zod para validación de formularios junto con react-hook-form
- Clases Tailwind directamente, NO CSS modules ni styled-components
- Componentes UI base de `@radix-ui/*` — NO instalar otras librerías UI

## APIs externas — variables de entorno clave
```
ANTHROPIC_API_KEY       # Claude AI
OPENAI_API_KEY          # Embeddings + Whisper
VOYAGE_API_KEY          # VoyageAI embeddings
TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_WHATSAPP_NUMBER
STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET
AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / R2_BUCKET_NAME / R2_ENDPOINT_URL
GOOGLE_CREDENTIALS_JSON # Google Calendar + TTS
DATABASE_URL            # PostgreSQL async (postgresql+asyncpg://...)
REDIS_URL
SENTRY_DSN
```

## Archivos críticos (leer antes de modificar)
- `backend/app/api/v1/webhooks.py` (29KB) — Twilio + Stripe events
- `backend/app/workers/tasks.py` (34KB) — Celery campaign tasks
- `backend/app/services/radio_service.py` (27KB) — AI radio content
- `backend/alembic/versions/` — migraciones; SIEMPRE crear nueva versión, NUNCA editar existentes

## Tests
- **Backend**: pytest + pytest-asyncio en `backend/tests/` y archivos `test_*.py` raíz backend
- **Frontend**: Vitest en `frontend/src/__tests__/`, Playwright en `frontend/e2e/`
- Correr backend tests: `cd backend && pytest`
- Correr frontend tests: `cd frontend && npm test`

## Docker / Deploy
- Dev: `docker-compose up` desde raíz
- Prod: Railway — ver `railway.json` y `RAILWAY_TROUBLESHOOTING.md`
- Worker separado: `Dockerfile.worker`
