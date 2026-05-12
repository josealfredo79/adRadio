"""
IaRadio — FastAPI application entry point.
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.core.redis import close_redis
from app.api.v1 import auth, contacts, campaigns, conversations, knowledge_base, webhooks, profile, payments, radio, orders, appointments

logger = logging.getLogger(__name__)

if settings.SENTRY_DSN:
    sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1)

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


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


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

