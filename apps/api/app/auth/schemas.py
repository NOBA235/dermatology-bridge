"""Pydantic v2 schemas for clinician authentication."""

import uuid
from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    """Clinician login credentials."""

    email: str
    password: str


class ClinicianOut(BaseModel):
    """Authenticated clinician profile."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID
    email: str
    full_name: str | None = None


class TokenResponse(BaseModel):
    """JWT access token response (HS256, no refresh tokens)."""

    access_token: str
    token_type: str = "bearer"
    clinician: ClinicianOut

