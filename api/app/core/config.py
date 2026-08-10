"""
Application configuration using Pydantic Settings.
All values are read from environment variables or .env file.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    APP_NAME: str = "TechScape AI API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # CORS
    FRONTEND_URL: str = "http://localhost:3000"
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://techscapeai.com",
        "https://www.techscapeai.com",
    ]

    # Supabase (use existing connectors)
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # Email (optional — for contact form notifications)
    SENDGRID_API_KEY: str = ""
    RESEND_API_KEY: str = ""
    NOTIFICATION_EMAIL: str = "hello@techscapeai.com"
    FROM_EMAIL: str = "noreply@techscapeai.com"

    # ── TechScape Workflow Platform — channel providers ──
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    WAPI_API_TOKEN: str = ""
    WAPI_BASE_URL: str = "https://api.wapi.ai"

    # ── TechScape AI agent (Claude) ──
    ANTHROPIC_API_KEY: str = ""
    AI_MODEL: str = "claude-sonnet-4-6"

    # ── GoGaga voice (Phase 2) — Plivo (+91 domestic voice) ──
    PLIVO_AUTH_ID: str = ""
    PLIVO_AUTH_TOKEN: str = ""
    PLIVO_PHONE_NUMBER: str = ""
    PUBLIC_BASE_URL: str = ""  # ngrok https URL in dev — Plivo needs a public webhook target
    # Plivo webhooks carry no JWT/business context, and there's no
    # phone-number-per-business registry yet (Phase 3 TODO). One global
    # PLIVO_PHONE_NUMBER can only realistically serve one tenant right
    # now, so that tenant is named explicitly here.
    PLIVO_BUSINESS_ID: str = ""

    # ── GoGaga voice (Phase 2) — STT/TTS ──
    SARVAM_API_KEY: str = ""     # Telugu / code-mix STT
    DEEPGRAM_API_KEY: str = ""   # English/Hindi STT (default engine)
    ELEVENLABS_API_KEY: str = ""  # TTS

    # ── TechScape auth ──
    JWT_SECRET: str = "change-me-in-prod"
    JWT_REFRESH_SECRET: str = "change-me-too-in-prod"
    JWT_ACCESS_TTL_MIN: int = 15
    JWT_REFRESH_TTL_DAYS: int = 7

    # Symmetric key (urlsafe base64, 32-byte) for ts_api_integrations.credentials_encrypted
    # If empty a key is derived from JWT_SECRET (DEV only).
    FERNET_KEY: str = ""

    # OAuth2 (optional)
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    OAUTH_REDIRECT_BASE: str = "http://localhost:5173"

    # ── Webhooks: signing secrets for inbound providers ──
    TWILIO_WEBHOOK_AUTH_TOKEN: str = ""  # falls back to TWILIO_AUTH_TOKEN if empty
    SENDGRID_WEBHOOK_PUBLIC_KEY: str = ""
    WAPI_WEBHOOK_SECRET: str = ""

    # ── Phase 3: Redis (T8 — call_feed pub/sub + JTI blacklist) ──
    # Falls back gracefully to in-process implementations if not set.
    REDIS_URL: str = ""  # e.g. redis://localhost:6379/0

    # Rate limiting
    RATE_LIMIT_CONTACT: int = 5  # requests per minute per IP
    RATE_LIMIT_NEWSLETTER: int = 3

    # ── Observability: alerting rules as code (app/core/alerting.py) ──
    # The periodic evaluator is OFF unless OBSERVABILITY_ALERTS=true; the
    # recording hooks are always live (they are O(1) appends).
    OBSERVABILITY_ALERTS: bool = False
    ALERT_CHECK_INTERVAL_SECONDS: int = 60
    ALERT_ERROR_RATE_PER_MIN: int = 10       # rule 1: captured events/min
    ALERT_VOICE_TURN_BUDGET_MS: int = 1100   # rule 2: ≤1.1s median mouth-to-ear SLO
    ALERT_VOICE_TURN_MIN_SAMPLES: int = 5    # rule 2: min turns before judging median
    ALERT_PAYMENT_SIG_FAILURES: int = 3      # rule 3: rejections per 60s window
    ALERT_COOLDOWN_SECONDS: int = 300        # per-rule re-fire suppression


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
