"""Application settings via pydantic-settings."""

from functools import lru_cache
import os
from pathlib import Path
import tempfile
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

IS_SERVERLESS = (
    os.environ.get("VERCEL") == "1"
    or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is not None
)
_RESOLVED_CONFIG_PATH = Path(__file__).resolve()
API_ROOT = _RESOLVED_CONFIG_PATH.parents[1]
_CANDIDATE_REPO_ROOT = (
    _RESOLVED_CONFIG_PATH.parents[3]
    if len(_RESOLVED_CONFIG_PATH.parents) > 3
    else API_ROOT
)
REPO_ROOT = (
    _CANDIDATE_REPO_ROOT
    if (_CANDIDATE_REPO_ROOT / "templates").exists()
    or (_CANDIDATE_REPO_ROOT / "apps").exists()
    else API_ROOT
)
WRITABLE_RUNTIME_DIR = (
    Path(tempfile.gettempdir()) / "dermobridge"
    if IS_SERVERLESS or not os.access(API_ROOT, os.W_OK)
    else REPO_ROOT
)
_DEFAULT_SQLITE_PATH = (
    (WRITABLE_RUNTIME_DIR / "dermobridge.db")
    if IS_SERVERLESS or not os.access(API_ROOT, os.W_OK)
    else (API_ROOT / "dermobridge.db")
)


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(API_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Dermatology Bridge API"
    DATABASE_URL: str = f"sqlite:///{_DEFAULT_SQLITE_PATH.as_posix()}"

    # Non-negotiable constraint: mock-first by default.
    ALLOW_LIVE_CALLS: bool = False
    YOUCAM_API_KEY: str = ""
    YOUCAM_BASE_URL: str = "https://yce-api-01.perfectcorp.com"

    # JWT config: HS256, single signing key, no refresh tokens.
    JWT_SECRET_KEY: str = "dev-only-hs256-signing-key-32-bytes-minimum"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480

    # Private object storage. Local filesystem remains the development default.
    STORAGE_BACKEND: str = "local"
    STORAGE_BUCKET: str = ""
    STORAGE_ENDPOINT_URL: str = ""
    STORAGE_ACCESS_KEY_ID: str = ""
    STORAGE_SECRET_ACCESS_KEY: str = ""
    STORAGE_REGION: str = "us-east-1"

    # Comma-separated browser origins for deployments that use a separate API host.
    CORS_ORIGINS: str = ""

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
    if settings.STORAGE_BACKEND not in {"local", "s3"}:
        raise RuntimeError("STORAGE_BACKEND must be either 'local' or 's3'.")
    if settings.STORAGE_BACKEND == "s3" and not all(
        (
            settings.STORAGE_BUCKET.strip(),
            settings.STORAGE_ENDPOINT_URL.strip(),
            settings.STORAGE_ACCESS_KEY_ID.strip(),
            settings.STORAGE_SECRET_ACCESS_KEY.strip(),
        )
    ):
        raise RuntimeError(
            "S3 storage requires STORAGE_BUCKET, STORAGE_ENDPOINT_URL, "
            "STORAGE_ACCESS_KEY_ID, and STORAGE_SECRET_ACCESS_KEY."
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    settings = Settings()
    verify_startup_invariants(settings)
    return settings
