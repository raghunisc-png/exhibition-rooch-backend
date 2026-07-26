"""
Application configuration.

All settings are loaded from environment variables (see .env.example at the
repo root). Using pydantic-settings gives us validation + sane defaults for
local development while still being fully configurable in production.
"""
from functools import lru_cache
from typing import List, Literal


from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Core ---
    ENV: Literal["development", "production", "test"] = "development"
    DATABASE_URL: str = "postgresql+psycopg://expo_user:expo_pass@localhost:5432/expo_invoices"

    # --- Auth ---
    JWT_SECRET_KEY: str = "insecure-dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    # --- Storage ---
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    UPLOAD_DIR: str = "uploads"
    S3_BUCKET: str = ""
    S3_REGION: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_ENDPOINT_URL: str = ""

    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # --- Twilio ---
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+918169029574"
    TWILIO_SMS_FROM: str = "+918169029574"

    # --- Company / invoice branding ---
    COMPANY_NAME: str = "Rooch Fashions"
    COMPANY_ADDRESS: str = ""
    COMPANY_GSTIN: str = ""

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def messaging_configured(self) -> bool:
        return bool(self.TWILIO_ACCOUNT_SID and self.TWILIO_AUTH_TOKEN)


@lru_cache
def get_settings() -> Settings:
    return Settings()
