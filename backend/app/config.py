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

    # Email (Resend — SMTP outbound is blocked on Railway's Hobby plan)
    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "IaRadio <noreply@iaradio.online>"

    # WhatsApp Cloud API de Meta — conexión directa
    # Clave de cifrado en reposo para tokens de Meta (AES-256-GCM).
    # Genera con: openssl rand -base64 32
    ENCRYPTION_KEY: str = ""
    META_GRAPH_BASE_URL: str = "https://graph.facebook.com"
    META_GRAPH_API_VERSION: str = "v21.0"
    # Token de verificación del webhook (handshake GET de Meta).
    # Genera con: openssl rand -hex 32
    META_WEBHOOK_VERIFY_TOKEN: str = ""
    # Opcional: App Secret de la app de Meta, para validar la firma
    # X-Hub-Signature-256 de cada evento del webhook.
    META_APP_SECRET: str = ""
    # Embedded Signup — "Conectar con Meta" (un clic, sin pegar tokens).
    # Se obtienen en developers.facebook.com → tu app → App Dashboard.
    META_APP_ID: str = ""
    # ID del "WhatsApp Embedded Signup configuration" (dashboard → WhatsApp → Embedded Signup).
    META_EMBEDDED_SIGNUP_CONFIG_ID: str = ""

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""

    # Anthropic — usado como fallback si OPENROUTER_MODEL no está configurado
    # (ver app/services/llm_client.py). Único proveedor de texto hasta 2026-07-31.
    ANTHROPIC_API_KEY: str = ""
    # Modelo de Claude a usar — configurable para migrar cuando Anthropic deprecate el actual
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

    # OpenRouter — adaptador de proveedor LLM intercambiable (port del patrón
    # de vocero-crm). Si OPENROUTER_API_KEY y OPENROUTER_MODEL están ambos
    # configurados, TODA la generación de texto (bot, campañas, Laboratorio,
    # banners) pasa por aquí en vez de Anthropic directo — permite usar
    # modelos gratis/baratos de OpenRouter (ver openrouter.ai/models) sin
    # tocar código, solo cambiando estas variables. Vacío = comportamiento
    # anterior sin cambios (Anthropic directo).
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = ""
    # Modelo aparte para el juez del Laboratorio (evaluación) — opcional, si
    # se omite usa OPENROUTER_MODEL. Igual que vocero-crm: separar el modelo
    # "conversacional" del "juez" permite, por ejemplo, un modelo barato para
    # el agente y uno más fuerte (o viceversa) solo para evaluar.
    OPENROUTER_JUDGE_MODEL: str = ""

    # OpenAI (Whisper transcription always; embeddings only if USE_OPENAI_EMBEDDINGS
    # is explicitly set — see embedding_service.py. Keeping these decoupled means
    # turning on Whisper (voice-note/audio-KB transcription) can never silently
    # switch the RAG embedding provider and desync it from already-stored vectors.
    OPENAI_API_KEY: str = ""
    USE_OPENAI_EMBEDDINGS: bool = False

    # Groq — free Whisper tier (2,000 req/day, no card required) used for
    # audio transcription: inbound WhatsApp voice notes + Knowledge Base audio.
    GROQ_API_KEY: str = ""
    # Groq también sirve chat completions (mismo API key, endpoint OpenAI-
    # compatible) con cuota gratis mucho mayor que el free tier de OpenRouter
    # (~14,400 req/día vs ~50/día) — ver app/services/llm_client.py. Si
    # GROQ_CHAT_MODEL está configurado, chat_completion() lo intenta primero,
    # antes de OpenRouter y de Anthropic. Vacío = comportamiento anterior sin
    # cambios (salta directo a OpenRouter/Anthropic).
    GROQ_CHAT_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_CHAT_MODEL: str = ""

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

    # Backend public base URL (used to generate audio URLs for WhatsApp)
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
