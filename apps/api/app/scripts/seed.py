"""Idempotent Phase 0 seed script: 1 clinic, 1 clinician, 1 empty patient (zero visits)."""

from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import hash_password
from app.config import get_settings
from app.db.models import Clinic, Clinician, Patient
from app.db.session import SessionLocal

DEFAULT_CLINIC_NAME = "Bridge Dermatology Clinic"
DEFAULT_CLINICIAN_NAME = "Dr. Maya Chen, MD"
DEFAULT_PATIENT_EXTERNAL_REF = "PT-0001"
DEFAULT_PATIENT_NAME = "Alex Rivera"
DEFAULT_PATIENT_DOB = date(1991, 4, 15)
DEFAULT_CONSENT_VERSION = "v1-2026-10"


def seed_phase0(db: Session) -> dict[str, str]:
    """Seed one clinic, one clinician, and one empty patient idempotently."""
    settings = get_settings()

    # 1. Clinic (lookup by name)
    clinic = db.execute(
        select(Clinic).where(Clinic.name == DEFAULT_CLINIC_NAME)
    ).scalar_one_or_none()
    if clinic is None:
        clinic = Clinic(name=DEFAULT_CLINIC_NAME)
        db.add(clinic)
        db.flush()

    # 2. Clinician (lookup by unique email)
    clinician_email = settings.SEED_CLINICIAN_EMAIL.strip().lower()
    clinician = db.execute(
        select(Clinician).where(Clinician.email == clinician_email)
    ).scalar_one_or_none()
    if clinician is None:
        clinician = Clinician(
            clinic_id=clinic.id,
            email=clinician_email,
            password_hash=hash_password(settings.SEED_CLINICIAN_PASSWORD),
            full_name=DEFAULT_CLINICIAN_NAME,
        )
        db.add(clinician)
        db.flush()

    # 3. Empty patient (lookup by clinic_id + external_ref; zero visits in Phase 0)
    patient = db.execute(
        select(Patient).where(
            Patient.clinic_id == clinic.id,
            Patient.external_ref == DEFAULT_PATIENT_EXTERNAL_REF,
        )
    ).scalar_one_or_none()
    if patient is None:
        patient = Patient(
            clinic_id=clinic.id,
            external_ref=DEFAULT_PATIENT_EXTERNAL_REF,
            full_name=DEFAULT_PATIENT_NAME,
            dob=DEFAULT_PATIENT_DOB,
            consent_version=DEFAULT_CONSENT_VERSION,
            notes="Phase 0 seeded patient (no visits yet).",
        )
        db.add(patient)
        db.flush()

    db.commit()
    return {
        "clinic_id": str(clinic.id),
        "clinician_id": str(clinician.id),
        "clinician_email": clinician.email,
        "patient_id": str(patient.id),
        "patient_external_ref": patient.external_ref or "",
    }


def main() -> None:
    """CLI entrypoint for seeding Phase 0 baseline data."""
    with SessionLocal() as db:
        summary = seed_phase0(db)
        print(f"Seeded Phase 0 data: {summary}")


if __name__ == "__main__":
    main()

