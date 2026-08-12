"""
Application configuration.

All settings are loaded from environment variables.

Pydantic Settings provides:
- Environment variable loading
- Type validation
- Sensible local-development defaults
- Production configurability
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    """
    Application settings.

    Values can be provided through environment variables
    or through the .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ========================================================
    # CORE
    # ========================================================

    ENV: Literal[
        "development",
        "production",
        "test",
    ] = "development"

    DATABASE_URL: str = (
        "postgresql+psycopg://"
        "expo_user:expo_pass"
        "@localhost:5432/"
        "expo_invoices"
    )

    # ========================================================
    # AUTH
    # ========================================================

    JWT_SECRET_KEY: str = (
        "insecure-dev-secret-change-me"
    )

    JWT_ALGORITHM: str = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=720,
        ge=1,
    )

    # ========================================================
    # STORAGE
    # ========================================================

    STORAGE_BACKEND: Literal[
        "local",
        "s3",
    ] = "local"

    UPLOAD_DIR: str = "uploads"

    S3_BUCKET: str = ""
    S3_REGION: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_ENDPOINT_URL: str = ""

    PUBLIC_BASE_URL: str = (
        "http://localhost:8000"
    )

    # ========================================================
    # TWILIO / MESSAGING
    # ========================================================

    TWILIO_ACCOUNT_SID: str = ""

    TWILIO_AUTH_TOKEN: str = ""

    TWILIO_WHATSAPP_FROM: str = (
        "whatsapp:+918169029574"
    )

    TWILIO_SMS_FROM: str = (
        "+918169029574"
    )

    # ========================================================
    # COMPANY / INVOICE BRANDING
    # ========================================================

    COMPANY_NAME: str = (
        "Rooch"
    )

    COMPANY_ADDRESS: str = ""

    COMPANY_GSTIN: str = ""

    # Optional explicit logo path.
    #
    # If empty, pdf.py will try its automatic
    # frontend/backend logo locations.

    COMPANY_LOGO_PATH: str = ""

    # ========================================================
    # CORS
    # ========================================================

    CORS_ORIGINS: str = (
        "http://localhost:5173"
    )

    # ========================================================
    # CORS HELPER
    # ========================================================

    @property
    def cors_origins_list(self) -> list[str]:
        """
        Convert comma-separated CORS origins into a list.

        Example:

            CORS_ORIGINS=
                http://localhost:5173,
                http://localhost:3000

        becomes:

            [
                "http://localhost:5173",
                "http://localhost:3000",
            ]
        """

        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    # ========================================================
    # MESSAGING HELPER
    # ========================================================

    @property
    def messaging_configured(self) -> bool:
        """
        Return True when the minimum Twilio credentials
        required for API usage are available.
        """

        return bool(
            self.TWILIO_ACCOUNT_SID
            and self.TWILIO_AUTH_TOKEN
        )


# ============================================================
# SETTINGS FACTORY
# ============================================================

@lru_cache
def get_settings() -> Settings:
    """
    Return the cached application settings instance.

    Caching ensures the entire application uses the same
    configuration object.
    """

    return Settings()