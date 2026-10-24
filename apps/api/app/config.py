"""Application settings via pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(API_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Dermatology Bridge API"
    DATABASE_URL: str = f"sqlite:///{(API_ROOT / 'dermobridge.db').as_posix()}"

    # Non-negotiable constraint: mock-first by default.
    ALLOW_LIVE_CALLS: bool = False
    YOUCAM_API_KEY: str = ""
    YOUCAM_BASE_URL: str = "https://yce-api-01.perfectcorp.com"

    # JWT config: HS256, single signing key, no refresh tokens.
    JWT_SECRET_KEY: str = "dev-only-hs256-signing-key-32-bytes-minimum"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480

    # Seed defaults
    SEED_CLINICIAN_EMAIL: str = "dr.chen@bridgederm.local"
    SEED_CLINICIAN_PASSWORD: str = "clinician-demo-pass"

    @field_validator("ALLOW_LIVE_CALLS", mode="before")
    @classmethod
    def validate_allow_live_calls(cls, value: Any) -> bool:
        """Fail fast if ALLOW_LIVE_CALLS is explicitly blank or unparseable."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("false", "0", "no"):
                return False
            if normalized in ("true", "1", "yes"):
                return True
            raise ValueError(
                f"ALLOW_LIVE_CALLS must be an explicit boolean ('true'/'false'), got {value!r}"
            )
        raise ValueError(f"Invalid type for ALLOW_LIVE_CALLS: {type(value).__name__}")


def verify_startup_invariants(settings: Settings) -> None:
    """Assert critical safety invariants at application startup."""
    if not isinstance(settings.ALLOW_LIVE_CALLS, bool):
        raise RuntimeError("ALLOW_LIVE_CALLS must be resolved to a boolean at startup.")
    if settings.ALLOW_LIVE_CALLS and not settings.YOUCAM_API_KEY.strip():
        raise RuntimeError(
            "ALLOW_LIVE_CALLS=true requires a non-empty YOUCAM_API_KEY."
        )
    if not settings.JWT_SECRET_KEY or len(settings.JWT_SECRET_KEY.strip()) < 16:
        raise RuntimeError("JWT_SECRET_KEY must be set and at least 16 characters.")
    if settings.JWT_ALGORITHM != "HS256":
        raise RuntimeError("Only HS256 JWT signing is permitted by architecture lock.")


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    settings = Settings()
    verify_startup_invariants(settings)
    return settings

