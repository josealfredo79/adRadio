from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # App
    APP_NAME: str = "IaRadio"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://localhost/iaradio"

    @property
    def database_url_safe(self) -> str:
        """Return DATABASE_URL ensuring SSL is used in production."""
        url = self.DATABASE_URL
        if not self.DEBUG and "ssl=" not in url:
            if "?" in url:
                url += "&ssl=require"
            else:
                url += "?ssl=require"
        return url

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # JWT
    SECRET_KEY: str = ""  # Must be set via environment variable in production
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Email
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    FROM_EMAIL: str = "noreply@iaradio.app"

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = ""
    # Comma-separated list of pre-approved WhatsApp numbers for the Pro pool
    # e.g. "+525511111111,+525522222222,+525533333333"
    TWILIO_NUMBER_POOL: str = ""
    # SID de la plantilla notificacion_informativa (MARKETING) para abrir ventana 24h
    TWILIO_INVITACION_TEMPLATE_SID: str = "HX5dc3c07019d22ed5b128df45d2ed1b15"
    # SID de la plantilla notificacion_audio_v2 (UTILITY) que sí puede enviarse fuera de ventana 24h
    TWILIO_UTILITY_TEMPLATE_SID: str = "HXd5f54a4479517e056e3dc216f95d1067"
    # SID de plantilla con botones interactivos Sí/No para confirmación de pedidos
    TWILIO_ORDER_CONFIRM_BUTTONS_SID: str = "HXef5e2a5ea81bc899605ffd5b18010029"
    # SID de plantilla con botones interactivos Sí/No para confirmación de citas
    TWILIO_APPOINTMENT_CONFIRM_BUTTONS_SID: str = "HX9424a04e30e608f3359c77d23a383864"

    @property
    def twilio_number_pool_list(self) -> list[str]:
        return [n.strip() for n in self.TWILIO_NUMBER_POOL.split(",") if n.strip()]

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    # Modelo de Claude a usar — configurable para migrar cuando Anthropic deprecate el actual
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

    # OpenAI (embeddings + Whisper)
    OPENAI_API_KEY: str = ""

    # Voyage AI (embeddings RAG)
    VOYAGE_API_KEY: str = ""
    # Delay en segundos entre llamadas a Voyage AI para embeddings.
    # Free tier: ~3 RPM → usa 22 s. Plan de pago: baja a 0 o 1.
    VOYAGE_EMBEDDING_DELAY_S: float = 22.0

    # Fish Audio (TTS de alta calidad para cuñas de radio)
    # Obtén tu API key en https://fish.audio/app/api-keys
    FISH_AUDIO_API_KEY: str = ""
    # ID de voz del locutor (opcional) — elige una voz en español en fish.audio/voice-library
    # Si está vacío, se usa el modelo por defecto (Fish Audio S2)
    FISH_AUDIO_VOICE_ID: str = ""

    # Google Cloud (Imagen 3 + TTS)
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_SERVICE_ACCOUNT_JSON: str = ""  # JSON string of service account key

    # Google Cloud TTS
    # Proveedor: "google" para Google Cloud Text-to-Speech (WaveNet)
    GOOGLE_TTS_PROVIDER: str = ""  # "google", "fish", "edge"
    GOOGLE_TTS_VOICE_NAME: str = "es-ES-Neural2-F"  # Voice name from Google Cloud

    # Google Calendar OAuth (for appointment sync)
    GOOGLE_CALENDAR_CLIENT_ID: str = ""
    GOOGLE_CALENDAR_CLIENT_SECRET: str = ""

    # Cloudflare R2
    CF_R2_ACCESS_KEY: str = ""
    CF_R2_SECRET_KEY: str = ""
    CF_R2_BUCKET: str = ""
    CF_R2_ENDPOINT: str = ""
    CF_R2_PUBLIC_URL: str = ""

    # Sentry
    SENTRY_DSN: str = ""

    # PostHog
    POSTHOG_API_KEY: str = ""

    # Backend public base URL (used to generate audio URLs for WhatsApp/Twilio)
    # Set to the tunnel or production URL, e.g. https://my-tunnel.loca.lt
    BASE_URL: str = "http://localhost:8000"

    # Frontend
    FRONTEND_URL: str = "http://localhost:5173"
    # Public frontend URL for external links (plans URL, SEO, etc.)
    # e.g. "https://app.iaradio.app"
    FRONTEND_PUBLIC_URL: str = ""

    # Widget static files base URL (CSS/JS served from this domain)
    # e.g. "https://www.iaradio.online"
    WIDGET_URL: str = ""

    # CORS — si no se setea via env var, permite FRONTEND_URL y localhost solo en DEBUG
    CORS_ORIGINS: list[str] = []

    @property
    def cors_origins(self) -> list[str]:
        origins = list(self.CORS_ORIGINS)
        if self.FRONTEND_URL and self.FRONTEND_URL not in origins:
            origins.append(self.FRONTEND_URL)
        if self.DEBUG and "http://localhost:5173" not in origins:
            origins.append("http://localhost:5173")
        return origins

    # Email verification
    EMAIL_VERIFICATION_TTL: int = 600  # 10 minutos

    # Allowed Hosts — validate Host header against this list in production.
    # Comma-separated, e.g. "api.iaradio.online,iaradio.online"
    ALLOWED_HOSTS: str = ""

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]

    # Connection pool sizes
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60  # segundos

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
