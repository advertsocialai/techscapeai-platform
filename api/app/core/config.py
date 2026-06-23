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

    # Rate limiting
    RATE_LIMIT_CONTACT: int = 5  # requests per minute per IP
    RATE_LIMIT_NEWSLETTER: int = 3


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
