from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AdRadio"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Email
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    FROM_EMAIL: str = "noreply@adradio.app"

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = ""
    # Comma-separated list of pre-approved WhatsApp numbers for the Pro pool
    # e.g. "+525511111111,+525522222222,+525533333333"
    TWILIO_NUMBER_POOL: str = ""

    @property
    def twilio_number_pool_list(self) -> list[str]:
        return [n.strip() for n in self.TWILIO_NUMBER_POOL.split(",") if n.strip()]

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""

    # Anthropic
    ANTHROPIC_API_KEY: str = ""

    # OpenAI (embeddings + Whisper)
    OPENAI_API_KEY: str = ""

    # Voyage AI (embeddings RAG)
    VOYAGE_API_KEY: str = ""

    # Google Cloud (Imagen 3)
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_SERVICE_ACCOUNT_JSON: str = ""  # JSON string of service account key

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

    # Frontend
    FRONTEND_URL: str = "http://localhost:5173"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "https://app.adradio.app"]

    # Email verification
    EMAIL_VERIFICATION_TTL: int = 600  # 10 minutos

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60  # segundos

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
