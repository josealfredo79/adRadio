# AdRadio v2.0 — Plataforma SaaS de Publicidad Inteligente por WhatsApp

**Stack:** React 18 + FastAPI + Neon PostgreSQL + pgvector + Celery + Redis + Claude 3.5 Sonnet + Twilio

## Estructura del proyecto

```
adradio/
├── backend/              # FastAPI + Celery
│   ├── app/
│   │   ├── api/v1/       # Endpoints REST
│   │   ├── models/       # SQLAlchemy ORM
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # Claude, RAG, Twilio, Stripe, R2
│   │   ├── workers/      # Celery tasks
│   │   ├── core/         # Auth, email, Redis
│   │   └── main.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/             # React + Vite + TailwindCSS
│   └── src/
│       ├── pages/        # Login, Register, Dashboard, Campañas, Contactos...
│       ├── components/   # Layout, componentes reutilizables
│       ├── contexts/     # AuthContext
│       └── lib/          # api.ts, utils.ts
├── docker-compose.yml    # Desarrollo local
└── railway.toml          # Deploy Railway
```

## Setup local rápido

```bash
# 1. Clonar y entrar al proyecto
cd adradio

# 2. Configurar backend
cd backend
cp .env.example .env
# Editar .env con tus API keys

# 3. Levantar con Docker Compose (recomendado)
cd ..
docker-compose up --build

# 4. Correr migraciones (primera vez)
docker-compose exec backend alembic upgrade head

# Frontend disponible en: http://localhost:5173
# API disponible en: http://localhost:8000
# Docs API: http://localhost:8000/docs (solo en DEBUG=true)
```

## Variables de entorno requeridas

Ver `backend/.env.example` para la lista completa.

Mínimas para desarrollo:
- `DATABASE_URL` — Neon PostgreSQL connection string
- `REDIS_URL` — Redis connection string
- `SECRET_KEY` — JWT secret (genera con `openssl rand -hex 32`)
- `ANTHROPIC_API_KEY` — Para Claude IA
- `OPENAI_API_KEY` — Para embeddings RAG

## Deploy en Railway

1. Crear proyecto en [railway.app](https://railway.app)
2. Agregar servicio PostgreSQL (o conectar Neon)
3. Agregar servicio Redis
4. Conectar repo de GitHub
5. Configurar variables de entorno
6. Railway detecta `railway.toml` automáticamente

## API endpoints principales

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Registro + verificación email |
| POST | `/api/v1/auth/login` | Login → JWT tokens |
| GET | `/api/v1/dashboard` | KPIs cacheados en Redis |
| GET/POST | `/api/v1/contacts` | Gestión de contactos |
| POST | `/api/v1/contacts/import-csv` | Importación masiva async |
| GET/POST | `/api/v1/campaigns` | Gestión de campañas |
| POST | `/api/v1/campaigns/generate-content` | Claude genera 3 variantes |
| POST | `/api/v1/knowledge-base/upload` | Sube archivo → embeddings |
| POST | `/api/v1/webhooks/twilio/incoming` | Webhook WhatsApp entrante |
| POST | `/api/v1/webhooks/stripe` | Webhook pagos Stripe |
| GET | `/api/v1/plans` | Ver planes disponibles |
| POST | `/api/v1/checkout/create-session` | Iniciar pago Stripe |

## Seguridad implementada

- ✅ JWT access token 1h + refresh token 7d con rotación
- ✅ bcrypt cost factor 12 para contraseñas
- ✅ Rate limiting por IP con Redis
- ✅ Validación MIME real en uploads (no solo extensión)
- ✅ Validación firma X-Twilio-Signature en webhooks
- ✅ Validación firma Stripe en webhooks
- ✅ Verificación de email obligatoria
- ✅ Auto-unsubscribe en palabras STOP/BAJA
- ✅ Protección CSRF, XSS, SQL injection (ORM parameterizado)

## Anti-baneo WhatsApp

- Delays aleatorios 25-90 segundos entre mensajes (Celery countdown)
- Solo horarios humanos 8am-9pm por zona horaria del contacto
- Warm-up gradual del número
- Variación de contenido con Claude por campaña
- Auto-blacklist en respuestas BAJA/STOP/NO QUIERO
