
"""Patient longitudinal visit listing and trend endpoints (GET /api/patients/{id}/visits, /trends)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import CLINICAL_DISCLAIMER
from app.api.schemas import (
    ConcernTrendOut,
    PatientFlagsResponse,
    PatientTrendsResponse,
    PatientVisitsResponse,
    TreatmentFlagOut,
    TrendDataPointOut,
    VisitOut,
)
from app.auth.middleware import get_current_clinician
from app.db.models import Clinician, ConcernScore, Patient, Visit
from app.db.session import get_db
from app.domain.concerns import CONCERN_DIRECTION, CONCERN_LABELS, CONCERN_LIST
from app.domain.flags import MDC_TABLE, compute_delta_and_pct, compute_verdict
from app.domain.severity import map_score_to_severity
from app.services.agent import regenerate_patient_flags
from app.services.report import (
    FHIRBundle,
    build_patient_fhir_bundle,
    build_patient_report_pdf,
)

router = APIRouter(prefix="/patients", tags=["patients"])


def _get_authorized_patient(
    db: Session,
    patient_id: uuid.UUID,
    clinician: Clinician,
) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None or patient.clinic_id != clinician.clinic_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found in clinician's clinic.",
        )
    return patient


@router.get("/{patient_id}/visits", response_model=PatientVisitsResponse)
def list_patient_visits(
    patient_id: uuid.UUID,
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
) -> PatientVisitsResponse:
    """Return all visits and concern scores for a patient ordered chronologically."""
    patient = _get_authorized_patient(db, patient_id, clinician)

    stmt = (
        select(Visit)
        .where(Visit.patient_id == patient.id)
        .options(selectinload(Visit.concern_scores))
        .order_by(Visit.visit_date.asc(), Visit.created_at.asc())
    )
    visits = list(db.execute(stmt).scalars().all())

    concern_order = {name: idx for idx, name in enumerate(CONCERN_LIST)}
    visit_outs: list[VisitOut] = []
    for visit in visits:
        sorted_scores = sorted(
            visit.concern_scores,
            key=lambda cs: concern_order.get(cs.concern, 999),
        )
        visit_out = VisitOut.model_validate(visit)
        visit_out.concern_scores = [
            visit_out.concern_scores[visit.concern_scores.index(cs)]
            for cs in sorted_scores
        ]
        visit_outs.append(visit_out)

    return PatientVisitsResponse(
        patient_id=patient.id,
        visit_count=len(visit_outs),
        visits=visit_outs,
        disclaimer=CLINICAL_DISCLAIMER,
    )


@router.get("/{patient_id}/trends", response_model=PatientTrendsResponse)
def get_patient_trends(
    patient_id: uuid.UUID,
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
) -> PatientTrendsResponse:
    """Compute per-concern longitudinal series, deltas vs baseline, severity buckets, and verdicts."""
    patient = _get_authorized_patient(db, patient_id, clinician)

    stmt = (
        select(Visit)
        .where(
            Visit.patient_id == patient.id,
            Visit.youcam_status == "success",
        )
        .options(selectinload(Visit.concern_scores))
        .order_by(Visit.visit_date.asc(), Visit.created_at.asc())
    )
    visits = list(db.execute(stmt).scalars().all())
    visit_count = len(visits)

    # Belt-and-braces invariant: all compared visits must share the same analysis_version
    versions = {v.analysis_version for v in visits}
    if len(versions) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot compute longitudinal trends across visits with mismatched "
                f"analysis_version values: {sorted(versions)}."
            ),
        )

    analysis_version = visits[0].analysis_version if visits else None
    baseline_visit = visits[0] if visit_count >= 1 else None
    latest_visit = visits[-1] if visit_count >= 2 else None
    days_between = (
        (latest_visit.visit_date - baseline_visit.visit_date).days
        if baseline_visit is not None and latest_visit is not None
        else None
    )

    # Map (visit_id, concern) -> ConcernScore for fast lookup
    scores_by_visit_concern: dict[tuple[uuid.UUID, str], ConcernScore] = {}
    for visit in visits:
        for cs in visit.concern_scores:
            scores_by_visit_concern[(visit.id, cs.concern)] = cs

    concern_trends: list[ConcernTrendOut] = []
    for concern in CONCERN_LIST:
        points: list[TrendDataPointOut] = []
        for visit in visits:
            cs_row = scores_by_visit_concern.get((visit.id, concern))
            if cs_row is not None:
                points.append(
                    TrendDataPointOut(
                        visit_id=visit.id,
                        visit_date=visit.visit_date,
                        score=cs_row.score,
                        severity=map_score_to_severity(concern, cs_row.score),
                    )
                )

        base_cs = (
            scores_by_visit_concern.get((baseline_visit.id, concern))
            if baseline_visit is not None
            else None
        )
        latest_cs = (
            scores_by_visit_concern.get((latest_visit.id, concern))
            if latest_visit is not None
            else None
        )

        baseline_score = base_cs.score if base_cs is not None else None
        baseline_severity = (
            map_score_to_severity(concern, baseline_score)
            if baseline_score is not None
            else None
        )
        latest_score = latest_cs.score if latest_cs is not None else None
        latest_severity = (
            map_score_to_severity(concern, latest_score)
            if latest_score is not None
            else None
        )

        delta, pct_change = compute_delta_and_pct(baseline_score, latest_score)
        verdict = compute_verdict(
            concern,
            baseline_score,
            latest_score,
            days_between=days_between if days_between is not None else 0,
            visit_count=visit_count,
        )

        concern_trends.append(
            ConcernTrendOut(
                concern=concern,
                label=CONCERN_LABELS[concern],
                direction=CONCERN_DIRECTION[concern],
                mdc=MDC_TABLE[concern],
                baseline_score=baseline_score,
                baseline_severity=baseline_severity,
                latest_score=latest_score,
                latest_severity=latest_severity,
                delta=delta,
                pct_change=pct_change,
                verdict=verdict,
                points=points,
            )
        )

    return PatientTrendsResponse(
        patient_id=patient.id,
        visit_count=visit_count,
        analysis_version=analysis_version,
        baseline_visit_id=baseline_visit.id if baseline_visit else None,
        latest_visit_id=latest_visit.id if latest_visit else None,
        baseline_date=baseline_visit.visit_date if baseline_visit else None,
        latest_date=latest_visit.visit_date if latest_visit else None,
        days_between=days_between,
        concerns=concern_trends,
        disclaimer=CLINICAL_DISCLAIMER,
    )


@router.post("/{patient_id}/flags/regenerate", response_model=PatientFlagsResponse)
def regenerate_flags_endpoint(
    patient_id: uuid.UUID,
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
) -> PatientFlagsResponse:
    """Idempotently recompute treatment_flags (delete-then-insert) and grounded hypotheses for a patient."""
    patient = _get_authorized_patient(db, patient_id, clinician)
    try:
        outcome = regenerate_patient_flags(db, patient.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return PatientFlagsResponse(
        patient_id=patient.id,
        visit_count=outcome.visit_count,
        top_concern_indices=outcome.top_concern_indices,
        top_concerns=outcome.top_concerns,
        summary=outcome.summary,
        used_fallback=outcome.used_fallback,
        flags=[TreatmentFlagOut.model_validate(f) for f in outcome.flags],
        disclaimer=CLINICAL_DISCLAIMER,
    )


@router.get("/{patient_id}/flags", response_model=PatientFlagsResponse)
def get_patient_flags_endpoint(
    patient_id: uuid.UUID,
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
) -> PatientFlagsResponse:
    """Return materialized treatment_flags and grounded summary for a patient."""
    patient = _get_authorized_patient(db, patient_id, clinician)
    outcome = regenerate_patient_flags(db, patient.id)
    return PatientFlagsResponse(
        patient_id=patient.id,
        visit_count=outcome.visit_count,
        top_concern_indices=outcome.top_concern_indices,
        top_concerns=outcome.top_concerns,
        summary=outcome.summary,
        used_fallback=outcome.used_fallback,
        flags=[TreatmentFlagOut.model_validate(f) for f in outcome.flags],
        disclaimer=CLINICAL_DISCLAIMER,
    )


@router.get("/{patient_id}/report.pdf")
def get_patient_report_pdf(
    patient_id: uuid.UUID,
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
) -> Response:
    """Render and return the 3-page A4 consultation PDF report for a patient."""
    patient = _get_authorized_patient(db, patient_id, clinician)
    pdf_bytes, _html_str, _ctx = build_patient_report_pdf(
        db,
        patient.id,
        clinician=clinician,
    )
    filename = f"dermobridge-report-{patient.external_ref or patient.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


@router.get("/{patient_id}/fhir", response_model=FHIRBundle)
def get_patient_fhir_export(
    patient_id: uuid.UUID,
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
) -> FHIRBundle:
    """Export all patient concern_scores as FHIR R4 Observation resources inside a Bundle."""
    patient = _get_authorized_patient(db, patient_id, clinician)
    return build_patient_fhir_bundle(db, patient.id)



