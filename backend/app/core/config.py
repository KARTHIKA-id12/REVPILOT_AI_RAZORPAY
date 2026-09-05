from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor .env resolution to the backend/ directory (two levels up from
# this file: app/core/config.py -> app/ -> backend/) rather than relying
# on pydantic-settings' default of resolving "env_file" relative to the
# CURRENT WORKING DIRECTORY. A relative path here silently picks a
# different .env — or none at all, falling back to in-code defaults —
# depending on whether a script is run from the repo root, from
# backend/, or anywhere else. This was a real bug found during a fresh-
# environment smoke test: running `python scripts/seed_demo.py` from the
# repo root loaded no .env at all (there wasn't one at the repo root),
# silently fell back to the default DATABASE_URL, and seeded the WRONG
# database — one that happened to already exist from prior work — instead
# of the fresh one just created for the test.
_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Central application configuration, sourced from environment variables.

    Nothing here has a real secret default — production values must come
    from the environment. See .env.example for the full variable list.
    """

    model_config = SettingsConfigDict(env_file=_BACKEND_DIR / ".env", extra="ignore")

    APP_NAME: str = "RevPilot AI"
    VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    DATABASE_URL: str = "postgresql+psycopg://revpilot:revpilot@localhost:5432/revpilot"

    JWT_SECRET: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    AI_PROVIDER: Literal["huggingface", "mock"] = "mock"
    AI_API_KEY: str | None = None
    AI_MODEL: str | None = None  # per-provider default used when unset; see app/agents/huggingface_provider.py

    PAYMENT_PROVIDER: Literal["razorpay", "mock"] = "mock"
    RAZORPAY_KEY_ID: str | None = None
    RAZORPAY_KEY_SECRET: str | None = None
    RAZORPAY_WEBHOOK_SECRET: str | None = None

    FRONTEND_URL: str = "http://localhost:5173"
    BACKEND_URL: str = "http://localhost:8000"

    DEMO_MODE: bool = True

    @model_validator(mode="after")
    def validate_deployment_safety(self):
        if self.ENVIRONMENT == "production":
            if self.DEMO_MODE:
                raise ValueError("DEMO_MODE must be false in production.")
            if not self.JWT_SECRET or self.JWT_SECRET in {"change-me-in-env", "dev-only-not-for-production"}:
                raise ValueError("JWT_SECRET must be explicitly configured in production.")
        return self

    @property
    def payment_mode_label(self) -> str:
        if self.PAYMENT_PROVIDER == "razorpay" and self.RAZORPAY_KEY_ID:
            return "razorpay_test"
        return "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
