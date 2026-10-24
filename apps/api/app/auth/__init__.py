"""Authentication package exports."""

from app.auth.jwt import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.auth.middleware import JWTAuthMiddleware, get_current_clinician
from app.auth.router import router as auth_router

__all__ = [
    "JWTAuthMiddleware",
    "auth_router",
    "create_access_token",
    "decode_access_token",
    "get_current_clinician",
    "hash_password",
    "verify_password",
]

