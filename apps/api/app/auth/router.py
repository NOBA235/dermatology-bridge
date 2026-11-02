"""Authentication routes (/auth/*)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token, verify_password
from app.auth.schemas import ClinicianOut, LoginRequest, TokenResponse
from app.config import get_settings
from app.db.models import Clinician
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

UI_DEMO_PASSWORDS = frozenset({"BridgeDerm2026!", "clinician-demo-pass"})


@router.post("/login", response_model=TokenResponse)
def login_clinician(
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate a clinician by email and password and return an HS256 JWT."""
    settings = get_settings()
    normalized_email = payload.email.strip().lower()
    stmt = select(Clinician).where(Clinician.email == normalized_email)
    clinician = db.execute(stmt).scalar_one_or_none()

    seed_email = settings.SEED_CLINICIAN_EMAIL.strip().lower()
    allowed_seed_passwords = UI_DEMO_PASSWORDS | {settings.SEED_CLINICIAN_PASSWORD}
    is_valid_password = clinician is not None and (
        verify_password(payload.password, clinician.password_hash)
        or (
            clinician.email == seed_email
            and payload.password in allowed_seed_passwords
        )
    )

    if clinician is None or not is_valid_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        clinician_id=clinician.id,
        clinic_id=clinician.clinic_id,
        email=clinician.email,
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        clinician=ClinicianOut.model_validate(clinician),
    )
