"""
IaRadio — FastAPI application entry point.
"""
import html
import logging
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.core.redis import close_redis
from app.core.rate_limiter import limiter
from app.services.analytics_service import flush as analytics_flush
from app.api.v1 import auth, contacts, campaigns, conversations, knowledge_base, webhooks, profile, payments, radio, orders, appointments, templates, template_seeds, team, automations, widget, analytics, admin, chat_demo, products
from app.api.v1 import user_webhooks, public_api, public_api_routes, public_site, meta_whatsapp, lab

logger = logging.getLogger(__name__)


class RequestIdFilter(logging.Filter):
    """Add request_id to log records when available."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", "-")
        return True


logging.getLogger().addFilter(RequestIdFilter())

if settings.SENTRY_DSN:
    sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1)

if settings.DEBUG and settings.STRIPE_SECRET_KEY:
    logger.warning("=" * 60)
    logger.warning("⚠️  DEBUG MODE ACTIVADO CON CREDENCIALES REALES")
    logger.warning("   NO uses DEBUG=true en producción")
    logger.warning("=" * 60)

# Rate limiter (imported from app.core.rate_limiter; built with Redis fallback)


def _warn_insecure_env() -> None:
    """Warn if .env has live secrets and is world-readable."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        perms = env_path.stat().st_mode
        if perms & 0o004:
            logger.warning("=" * 60)
            logger.warning("SECURITY: .env is world-readable (chmod 600 recommended)")
            logger.warning("=" * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _warn_insecure_env()
    if not settings.DEBUG:
        if not settings.allowed_hosts_list:
            raise RuntimeError(
                "ALLOWED_HOSTS must be configured in production. "
                "Set it via environment variable, e.g. ALLOWED_HOSTS=api.iaradio.online,iaradio.online"
            )
        if settings.SECRET_KEY in ("", "change-me-in-production"):
            raise RuntimeError("SECRET_KEY must be set in production")
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


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP to HTTPS in production."""
    async def dispatch(self, request: Request, call_next):
        if not settings.DEBUG and request.headers.get("x-forwarded-proto", "") == "http":
            url = str(request.url).replace("http://", "https://", 1)
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url, status_code=status.HTTP_301_MOVED_PERMANENTLY)
        return await call_next(request)


class AllowedHostsMiddleware(BaseHTTPMiddleware):
    """Validate Host header against ALLOWED_HOSTS in production."""
    async def dispatch(self, request: Request, call_next):
        if not settings.DEBUG and settings.allowed_hosts_list:
            host = request.headers.get("host", "").split(":")[0]
            if host not in settings.allowed_hosts_list and host != "localhost":
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Host no permitido"},
                )
        return await call_next(request)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Inject X-Request-ID for tracing requests across services."""
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        logger = logging.getLogger("app")
        # Make the request ID available to handlers via request.state
        request.state.request_id = req_id
        return response


class WidgetCORSMiddleware(BaseHTTPMiddleware):
    """The main CORSMiddleware below only allows FRONTEND_URL (this app's own
    dashboard) — but /widget/chat and /widget/preview are meant to be
    embedded on arbitrary advertiser websites, so they need
    Access-Control-Allow-Origin: * regardless of that allowlist. Neither
    route reads cookies or auth headers, so a wildcard origin here doesn't
    expose any authenticated data. Registered as the outermost middleware
    (added last) so it can short-circuit the OPTIONS preflight before the
    stricter CORSMiddleware ever sees it."""
    WIDGET_PATHS = (
        f"{settings.API_PREFIX}/widget/chat/",
        f"{settings.API_PREFIX}/widget/preview/",
        f"{settings.API_PREFIX}/widget/lead/",
    )

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith(self.WIDGET_PATHS):
            return await call_next(request)
        if request.method == "OPTIONS":
            from starlette.responses import Response as StarletteResponse
            return StarletteResponse(status_code=200, headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Max-Age": "600",
            })
        response = await call_next(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        widget_url = settings.WIDGET_URL or ""
        api_url = settings.FRONTEND_PUBLIC_URL or ""
        csp_parts = ["default-src 'self'"]
        if widget_url:
            csp_parts.append(f"script-src 'self' {widget_url} https://js.stripe.com https://connect.facebook.net")
            csp_parts.append(f"style-src 'self' 'unsafe-inline' {widget_url}")
        else:
            csp_parts.append("script-src 'self' https://js.stripe.com https://connect.facebook.net")
            csp_parts.append("style-src 'self' 'unsafe-inline'")
        csp_parts.append("img-src 'self' data: blob: https:")
        csp_parts.append("frame-src 'self' https://js.stripe.com https://www.facebook.com https://facebook.com")
        connect_src = ["'self'"]
        if api_url:
            connect_src.append(api_url)
        connect_src.append("https://api.stripe.com")
        csp_parts.append(f"connect-src {' '.join(connect_src)}")
        csp = "; ".join(csp_parts)
        response.headers["Content-Security-Policy"] = csp
        if request.app.debug:
            response.headers["X-Debug"] = "1"
        return response


app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(AllowedHostsMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(WidgetCORSMiddleware)

# Routers
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(profile.router, prefix=settings.API_PREFIX)
app.include_router(meta_whatsapp.router, prefix=settings.API_PREFIX)
app.include_router(lab.router, prefix=settings.API_PREFIX)
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
app.include_router(products.router, prefix=settings.API_PREFIX)
app.include_router(widget.router, prefix=settings.API_PREFIX)
app.include_router(analytics.router, prefix=settings.API_PREFIX)
app.include_router(user_webhooks.router, prefix=settings.API_PREFIX)
app.include_router(admin.router, prefix=settings.API_PREFIX)
app.include_router(public_api.router, prefix=settings.API_PREFIX)
app.include_router(public_api_routes.router, prefix=settings.API_PREFIX)
app.include_router(public_site.router, prefix=settings.API_PREFIX)
app.include_router(public_site.product_router, prefix=settings.API_PREFIX)
app.include_router(chat_demo.router, prefix=settings.API_PREFIX)

# Serve WhatsApp widget static files publicly
_WIDGET_DIR = Path(__file__).parent / "static" / "widget"
if _WIDGET_DIR.is_dir():
    app.mount("/widget", StaticFiles(directory=str(_WIDGET_DIR)), name="widget-static")


@app.get("/health")
async def health():
    if not settings.DEBUG:
        return {"status": "ok"}

    import stripe as stripe_lib
    from sqlalchemy import text
    from app.database import engine

    checks = {}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    try:
        import redis as sync_redis
        r = sync_redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        r.ping()
        r.close()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

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

# Two shapes both point at an individual shareable product page:
# /sitio/{slug}/producto/{product_id} (business published a landing page) and
# /p/{advertiser_id}/{product_id} (works regardless — see public_site.py's
# product_router docstring: WhatsApp adoption and landing-page adoption
# don't overlap reliably enough to make either a hard dependency of the
# other). iaradio.online is a 100%-client-rendered SPA (no SSR), so the
# dynamic <meta property="og:*"> tags ProductDetailPage sets via
# react-helmet-async are invisible to link-preview crawlers that don't
# execute JS (WhatsApp's own crawler notably doesn't) — they only ever see
# raw index.html, which has one fixed og:image for the whole site. These
# regexes + the crawler check below intercept exactly those two route
# shapes for known crawler User-Agents and hand back real per-product HTML
# instead, so pasting a product link into WhatsApp shows that product's
# actual photo/name, not the generic site preview. Real browsers (and any
# UA not in the crawler list) fall through to the normal SPA unchanged.
_PRODUCT_PAGE_RE = re.compile(r"^sitio/([^/]+)/producto/([0-9a-fA-F-]{36})$")
_PRODUCT_PAGE_BY_ID_RE = re.compile(r"^p/([0-9a-fA-F-]{36})/([0-9a-fA-F-]{36})$")
_CRAWLER_UA_RE = re.compile(
    r"facebookexternalhit|WhatsApp|Twitterbot|Slackbot|LinkedInBot|TelegramBot|Discordbot",
    re.IGNORECASE,
)


async def _render_product_og_html(
    product_id: str, base_url: str, *, slug: str | None = None, advertiser_id: str | None = None,
) -> str | None:
    """Exactly one of slug/advertiser_id must be given — whichever route
    shape matched in serve_spa below."""
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.product import Product
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        if slug is not None:
            user_result = await db.execute(select(User).where(User.slug == slug.lower()))
        else:
            user_result = await db.execute(select(User).where(User.id == uuid.UUID(advertiser_id)))
        user = user_result.scalar_one_or_none()
        if not user:
            return None
        product_result = await db.execute(
            select(Product).where(
                Product.id == uuid.UUID(product_id),
                Product.advertiser_id == user.id,
                Product.active.is_(True),
            )
        )
        product = product_result.scalar_one_or_none()
        if not product:
            return None

    title = html.escape(f"{product.name} — {user.business_name or 'IaRadio'}")
    description = html.escape(product.description or f"{product.name} en {user.business_name or ''}".strip())
    image = html.escape(product.photo_url) if product.photo_url else f"{base_url}/og-image.png"
    path = f"sitio/{slug}/producto/{product_id}" if slug is not None else f"p/{advertiser_id}/{product_id}"
    page_url = html.escape(f"{base_url}/{path}")

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta property="og:type" content="product">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:image" content="{image}">
<meta property="og:url" content="{page_url}">
<meta name="twitter:card" content="summary_large_image">
<meta http-equiv="refresh" content="0;url={page_url}">
</head>
<body>Redirigiendo…</body>
</html>"""


if _SPA_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_SPA_DIR / "assets")), name="spa-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str, request: Request):
        is_crawler = _CRAWLER_UA_RE.search(request.headers.get("user-agent", ""))
        product_match = _PRODUCT_PAGE_RE.match(full_path)
        product_by_id_match = _PRODUCT_PAGE_BY_ID_RE.match(full_path) if not product_match else None

        if (product_match or product_by_id_match) and is_crawler:
            base_url = str(request.base_url).rstrip("/")
            if product_match:
                og_html = await _render_product_og_html(
                    product_match.group(2), base_url, slug=product_match.group(1),
                )
            else:
                og_html = await _render_product_og_html(
                    product_by_id_match.group(2), base_url, advertiser_id=product_by_id_match.group(1),
                )
            if og_html:
                return HTMLResponse(og_html)

        # Serve a real file if it exists (favicon, og-image, etc.)
        candidate = _SPA_DIR / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_SPA_DIR / "index.html"))
# Trigger deployment
