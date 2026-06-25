"""
IaRadio — FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.core.redis import close_redis
from app.services.analytics_service import flush as analytics_flush
from app.api.v1 import auth, contacts, campaigns, conversations, knowledge_base, webhooks, profile, payments, radio, orders, appointments, templates, template_seeds, team, automations, widget, analytics, admin
from app.api.v1 import user_webhooks, public_api, public_api_routes

logger = logging.getLogger(__name__)

if settings.SENTRY_DSN:
    sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1)

if settings.DEBUG and (settings.TWILIO_AUTH_TOKEN or settings.STRIPE_SECRET_KEY):
    logger.warning("=" * 60)
    logger.warning("⚠️  DEBUG MODE ACTIVADO CON CREDENCIALES REALES")
    logger.warning("   Twilio signature validation está DESHABILITADA")
    logger.warning("   NO uses DEBUG=true en producción")
    logger.warning("=" * 60)

# Rate limiter — intenta usar Redis para que el límite sea GLOBAL entre todos los workers.
# Si Redis no está disponible al arrancar (ej. primer deploy), cae a memoria local como fallback.
# Esto evita que cada proceso Uvicorn tenga un contador independiente en producción.
def _build_limiter() -> Limiter:
    try:
        import redis as sync_redis
        r = sync_redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        r.ping()
        storage_uri = settings.REDIS_URL
        logger.info("[RateLimit] Backend: Redis (%s)", settings.REDIS_URL)
    except Exception:
        storage_uri = "memory://"
        logger.warning(
            "[RateLimit] Redis no disponible al arrancar — usando memoria local. "
            "El límite NO será global entre múltiples workers."
        )
    return Limiter(
        key_func=get_remote_address,
        storage_uri=storage_uri,
        default_limits=["200/minute"],
    )

limiter = _build_limiter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    analytics_flush()
    await close_redis()


app = FastAPI(
    title="IaRadio API",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.app.debug:
            response.headers["X-Debug"] = "1"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(profile.router, prefix=settings.API_PREFIX)
app.include_router(contacts.router, prefix=settings.API_PREFIX)
app.include_router(campaigns.router, prefix=settings.API_PREFIX)
app.include_router(conversations.router, prefix=settings.API_PREFIX)
app.include_router(knowledge_base.router, prefix=settings.API_PREFIX)
app.include_router(payments.router, prefix=settings.API_PREFIX)
app.include_router(webhooks.router, prefix=settings.API_PREFIX)
app.include_router(radio.router, prefix=settings.API_PREFIX)
app.include_router(orders.router, prefix=settings.API_PREFIX)
app.include_router(appointments.router, prefix=settings.API_PREFIX)
app.include_router(templates.router, prefix=settings.API_PREFIX)
app.include_router(template_seeds.router, prefix=settings.API_PREFIX)
app.include_router(team.router, prefix=settings.API_PREFIX)
app.include_router(automations.router, prefix=settings.API_PREFIX)
app.include_router(widget.router, prefix=settings.API_PREFIX)
app.include_router(analytics.router, prefix=settings.API_PREFIX)
app.include_router(user_webhooks.router, prefix=settings.API_PREFIX)
app.include_router(admin.router, prefix=settings.API_PREFIX)
app.include_router(public_api.router, prefix=settings.API_PREFIX)
app.include_router(public_api_routes.router, prefix=settings.API_PREFIX)

# Serve WhatsApp widget static files publicly
_WIDGET_DIR = Path(__file__).parent / "static" / "widget"
if _WIDGET_DIR.is_dir():
    app.mount("/widget", StaticFiles(directory=str(_WIDGET_DIR)), name="widget-static")


@app.get("/health")
async def health():
    import stripe as stripe_lib
    from sqlalchemy import text
    from app.database import engine

    checks = {}

    # Database check
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Redis check
    try:
        import redis as sync_redis
        r = sync_redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        r.ping()
        r.close()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # Stripe check
    if settings.STRIPE_SECRET_KEY:
        try:
            stripe_lib.api_key = settings.STRIPE_SECRET_KEY
            stripe_lib.Balance.retrieve()
            checks["stripe"] = "ok"
        except Exception as e:
            checks["stripe"] = f"error: {e}"
    else:
        checks["stripe"] = "not_configured"

    all_ok = all(v == "ok" for v in checks.values() if v != "not_configured")
    return {
        "status": "ok" if all_ok else "degraded",
        "version": settings.APP_VERSION,
        "checks": checks,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    if settings.SENTRY_DSN:
        sentry_sdk.capture_exception(exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Error interno del servidor"},
    )


# Serve built React SPA (only present in production / Railway build)
_SPA_DIR = Path(__file__).parent / "static" / "dist"
if _SPA_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_SPA_DIR / "assets")), name="spa-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Serve a real file if it exists (favicon, og-image, etc.)
        candidate = _SPA_DIR / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_SPA_DIR / "index.html"))
# Trigger deployment
