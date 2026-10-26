"""Idempotent database seed script for Phase 0 baseline and Phase 2 3-visit longitudinal demo patient."""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import hash_password
from app.config import get_settings
from app.db.models import Clinic, Clinician, ConcernScore, Patient, Visit
from app.db.session import SessionLocal
from app.domain.concerns import ANALYSIS_VERSION, CONCERN_LIST
from app.domain.severity import map_score_to_severity

DEFAULT_CLINIC_NAME = "Bridge Dermatology Clinic"
DEFAULT_CLINICIAN_NAME = "Dr. Maya Chen, MD"

# Phase 0 empty patient (kept with zero visits for empty/single-visit baseline tests)
DEFAULT_PATIENT_EXTERNAL_REF = "PT-0001"
DEFAULT_PATIENT_NAME = "Alex Rivera"
DEFAULT_PATIENT_DOB = date(1991, 4, 15)
DEFAULT_CONSENT_VERSION = "v1-2026-10"

# Phase 2 demo patient with 3 pre-computed visits spanning 90 days
DEMO_PATIENT_EXTERNAL_REF = "PT-DEMO-001"
DEMO_PATIENT_NAME = "Elena Rostova"
DEMO_PATIENT_DOB = date(1989, 11, 23)

DEMO_VISITS_SPEC: tuple[dict[str, Any], ...] = (
    {
        "visit_date": date(2026, 7, 15),
        "chief_complaint": (
            "Inflammatory acne and post-inflammatory redness on cheeks; skin feels dehydrated"
        ),
        "routine_text": "Foaming salicylic cleanser twice daily, lightweight gel lotion",
        "treatment_changes": "Initiated nightly adapalene 0.1% gel and ceramide barrier cream",
        "youcam_file_id": "yc_file_seed_demo_v1",
        "youcam_task_id": "yc_task_seed_demo_v1",
        "scores": {
            "acne": Decimal("68.00"),
            "wrinkle": Decimal("31.00"),
            "pores": Decimal("54.00"),
            "texture": Decimal("44.00"),
            "redness": Decimal("62.00"),
            "oiliness": Decimal("64.00"),
            "moisture": Decimal("42.00"),
            "radiance": Decimal("48.00"),
            "firmness": Decimal("72.00"),
            "dark_circle_v2": Decimal("38.00"),
            "dark_spot": Decimal("32.00"),
            "skin_tone": Decimal("66.00"),
        },
    },
    {
        "visit_date": date(2026, 8, 29),
        "chief_complaint": (
            "Acne lesions decreasing; mild dryness and new sun spots after August travel"
        ),
        "routine_text": "Gentle hydrating cleanser, ceramide cream, adapalene 0.1% nightly",
        "treatment_changes": (
            "Added niacinamide 5% serum; switched to mineral SPF 30 (inconsistent reapplication outdoors)"
        ),
        "youcam_file_id": "yc_file_seed_demo_v2",
        "youcam_task_id": "yc_task_seed_demo_v2",
        "scores": {
            "acne": Decimal("51.00"),
            "wrinkle": Decimal("30.50"),
            "pores": Decimal("50.00"),
            "texture": Decimal("47.00"),
            "redness": Decimal("49.00"),
            "oiliness": Decimal("55.00"),
            "moisture": Decimal("58.00"),
            "radiance": Decimal("56.00"),
            "firmness": Decimal("73.00"),
            "dark_circle_v2": Decimal("39.00"),
            "dark_spot": Decimal("41.00"),
            "skin_tone": Decimal("65.00"),
        },
    },
    {
        "visit_date": date(2026, 10, 13),
        "chief_complaint": (
            "Acne and hydration much improved, but hyperpigmentation spots on malar cheeks more noticeable"
        ),
        "routine_text": "Gentle cleanser, niacinamide 5%, ceramide cream, adapalene 0.1% nightly",
        "treatment_changes": (
            "Added glycolic acid 10% toner 3x/week two weeks ago without strict broad-spectrum SPF"
        ),
        "youcam_file_id": "yc_file_seed_demo_v3",
        "youcam_task_id": "yc_task_seed_demo_v3",
        "scores": {
            "acne": Decimal("38.00"),
            "wrinkle": Decimal("29.50"),
            "pores": Decimal("46.00"),
            "texture": Decimal("53.00"),
            "redness": Decimal("41.00"),
            "oiliness": Decimal("49.00"),
            "moisture": Decimal("71.00"),
            "radiance": Decimal("63.00"),
            "firmness": Decimal("74.00"),
            "dark_circle_v2": Decimal("39.50"),
            "dark_spot": Decimal("51.00"),
            "skin_tone": Decimal("64.50"),
        },
    },
)


def _build_seed_raw_result(
    task_id: str,
    file_id: str,
    scores: dict[str, Decimal],
) -> dict[str, Any]:
    """Construct a canonical YouCam S2S v2.0 raw_result payload for a seeded visit."""
    results_list: list[dict[str, Any]] = []
    for concern in CONCERN_LIST:
        val = float(scores[concern])
        results_list.append(
            {
                "concern": concern,
                "type": concern,
                "score": val,
                "ui_score": val,
                "raw_score": round(val / 100.0, 4),
                "mask_url": f"https://yce-ephemeral.youcam.local/masks/{task_id}/{concern}.png",
            }
        )
    return {
        "status": 200,
        "result": {
            "task_id": task_id,
            "src_file_id": file_id,
            "task_status": "success",
            "analysis_version": ANALYSIS_VERSION,
            "prerender": True,
            "results": results_list,
        },
    }


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

    # 3. Empty patient (lookup by clinic_id + external_ref; zero visits)
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


def seed_demo_longitudinal(db: Session) -> dict[str, Any]:
    """Seed the 3-visit longitudinal demo patient (~90 days) idempotently."""
    base_info = seed_phase0(db)
    clinic = db.execute(
        select(Clinic).where(Clinic.name == DEFAULT_CLINIC_NAME)
    ).scalar_one()

    demo_patient = db.execute(
        select(Patient).where(
            Patient.clinic_id == clinic.id,
            Patient.external_ref == DEMO_PATIENT_EXTERNAL_REF,
        )
    ).scalar_one_or_none()
    if demo_patient is None:
        demo_patient = Patient(
            clinic_id=clinic.id,
            external_ref=DEMO_PATIENT_EXTERNAL_REF,
            full_name=DEMO_PATIENT_NAME,
            dob=DEMO_PATIENT_DOB,
            consent_version=DEFAULT_CONSENT_VERSION,
            notes=(
                "Longitudinal demo patient with 3 pre-computed visits over 90 days "
                "(improving acne/moisture/redness, stalled wrinkle/firmness, worsening dark_spot/texture)."
            ),
        )
        db.add(demo_patient)
        db.flush()

    visit_ids: list[str] = []
    for idx, spec in enumerate(DEMO_VISITS_SPEC, start=1):
        visit_date: date = spec["visit_date"]
        visit = db.execute(
            select(Visit).where(
                Visit.patient_id == demo_patient.id,
                Visit.visit_date == visit_date,
            )
        ).scalar_one_or_none()

        scores_map: dict[str, Decimal] = spec["scores"]
        task_id: str = spec["youcam_task_id"]
        file_id: str = spec["youcam_file_id"]

        if visit is None:
            visit = Visit(
                patient_id=demo_patient.id,
                visit_date=visit_date,
                chief_complaint=spec["chief_complaint"],
                routine_text=spec["routine_text"],
                treatment_changes=spec["treatment_changes"],
                analysis_version=ANALYSIS_VERSION,
                image_storage_key=f"patients/{demo_patient.id}/visits/seed_v{idx}/selfie.jpg",
                youcam_file_id=file_id,
                youcam_task_id=task_id,
                youcam_status="success",
                raw_result=_build_seed_raw_result(task_id, file_id, scores_map),
            )
            db.add(visit)
            db.flush()

        for concern in CONCERN_LIST:
            existing_score = db.execute(
                select(ConcernScore).where(
                    ConcernScore.visit_id == visit.id,
                    ConcernScore.concern == concern,
                )
            ).scalar_one_or_none()
            if existing_score is None:
                score_val = scores_map[concern]
                db.add(
                    ConcernScore(
                        visit_id=visit.id,
                        concern=concern,
                        score=score_val,
                        severity=map_score_to_severity(concern, score_val),
                        mask_url=f"https://yce-ephemeral.youcam.local/masks/{task_id}/{concern}.png",
                        mask_storage_key=f"patients/{demo_patient.id}/visits/{visit.id}/masks/{concern}.png",
                    )
                )

        visit_ids.append(str(visit.id))

    db.commit()
    return {
        **base_info,
        "demo_patient_id": str(demo_patient.id),
        "demo_patient_external_ref": demo_patient.external_ref,
        "demo_visit_ids": visit_ids,
    }


def main() -> None:
    """CLI entrypoint for seeding baseline and longitudinal demo data."""
    with SessionLocal() as db:
        summary = seed_demo_longitudinal(db)
        print(f"Seeded Dermatology Bridge data: {summary}")


if __name__ == "__main__":
    main()
