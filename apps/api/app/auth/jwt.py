"""Password hashing and HS256 JWT token utilities (single signing key, no refresh tokens)."""

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

import bcrypt
import jwt

from app.config import get_settings

CAPTURE_TOKEN_DEFAULT_TTL_MINUTES = 30


def hash_password(plain_password: str) -> str:
    """Hash a clinician password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def create_access_token(
    *,
    clinician_id: uuid.UUID,
    clinic_id: uuid.UUID,
    email: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Issue a signed HS256 JWT access token for a clinician."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": str(clinician_id),
        "clinic_id": str(clinic_id),
        "email": email,
        "purpose": "clinician_auth",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify and decode an HS256 JWT access token."""
    settings = get_settings()
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )


def create_capture_token(
    *,
    patient_id: uuid.UUID,
    clinic_id: uuid.UUID,
    clinician_id: uuid.UUID,
    ttl_minutes: int = CAPTURE_TOKEN_DEFAULT_TTL_MINUTES,
) -> str:
    """Issue a signed, short-lived HS256 capture token for patient mobile selfie upload."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ttl_minutes)
    payload: dict[str, Any] = {
        "sub": str(patient_id),
        "patient_id": str(patient_id),
        "clinic_id": str(clinic_id),
        "issued_by": str(clinician_id),
        "purpose": "patient_capture",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_capture_token(token: str) -> dict[str, Any]:
    """Verify and decode a signed patient capture token."""
    claims = decode_access_token(token)
    if claims.get("purpose") != "patient_capture":
        raise jwt.InvalidTokenError("Token is not a valid patient_capture token.")
    return claims
