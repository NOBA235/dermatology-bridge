"""Patient longitudinal visit listing, trend, medication, and correlation endpoints."""

from datetime import date
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app import CLINICAL_DISCLAIMER
from app.api.schemas import (
    CaptureTokenOut,
    ConcernResponseSummaryOut,
    ConcernTrendOut,
    MedicationCorrelationOut,
    PatientCreateRequest,
    PatientFlagsResponse,
    PatientListResponse,
    PatientMedicationCreate,
    PatientMedicationCorrelationsResponse,
    PatientMedicationListResponse,
    PatientMedicationOut,
    PatientOut,
    PatientTrendsResponse,
    PatientVisitsResponse,
    TreatmentFlagOut,
    TrendDataPointOut,
    VisitOut,
)
from app.auth.jwt import CAPTURE_TOKEN_DEFAULT_TTL_MINUTES, create_capture_token
from app.auth.middleware import get_current_clinician
from app.db.models import Clinician, ConcernScore, Patient, PatientMedication, Visit
from app.db.session import get_db
from app.domain.concerns import CONCERN_DIRECTION, CONCERN_LABELS, CONCERN_LIST
from app.domain.flags import MDC_TABLE, compute_delta_and_pct, compute_verdict
from app.domain.medications import cross_reference_medication
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


def _to_patient_out(patient: Patient) -> PatientOut:
    successful_visits = [
        v for v in patient.visits if v.youcam_status == "success"
    ]
    latest_date = (
        max(v.visit_date for v in successful_visits)
        if successful_visits
        else None
    )
    out = PatientOut.model_validate(patient)
    out.visit_count = len(successful_visits)
    out.latest_visit_date = latest_date
    out.disclaimer = CLINICAL_DISCLAIMER
    return out


@router.get("", response_model=PatientListResponse)
def list_patients(
    q: str | None = Query(default=None, description="Search by patient name or chart ref"),
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
) -> PatientListResponse:
    """List and search patients in the authenticated clinician's clinic."""
    stmt = (
        select(Patient)
        .where(Patient.clinic_id == clinician.clinic_id)
        .options(selectinload(Patient.visits))
        .order_by(Patient.created_at.desc())
    )
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Patient.full_name.ilike(pattern),
                Patient.external_ref.ilike(pattern),
                Patient.notes.ilike(pattern),
            )
        )
    patients = list(db.execute(stmt).scalars().all())
    items = [_to_patient_out(p) for p in patients]
    return PatientListResponse(
        patients=items,
        total=len(items),
        disclaimer=CLINICAL_DISCLAIMER,
    )


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def create_patient(
    payload: PatientCreateRequest,
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
) -> PatientOut:
    """Create a new patient record in the authenticated clinician's clinic."""
    cleaned_name = payload.full_name.strip()
    if not cleaned_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Patient full_name cannot be blank.",
        )

    patient = Patient(
        clinic_id=clinician.clinic_id,
        full_name=cleaned_name,
        external_ref=payload.external_ref.strip() if payload.external_ref else None,
        dob=payload.dob,
        consent_version=payload.consent_version or "v1-2026-10",
        notes=payload.notes,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return _to_patient_out(patient)


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient_detail(
    patient_id: uuid.UUID,
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
) -> PatientOut:
    """Return a single patient profile with visit count."""
    stmt = (
        select(Patient)
        .where(
            Patient.id == patient_id,
            Patient.clinic_id == clinician.clinic_id,
        )
        .options(selectinload(Patient.visits))
    )
    patient = db.execute(stmt).scalar_one_or_none()
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found in clinician's clinic.",
        )
    return _to_patient_out(patient)


@router.post("/{patient_id}/capture-token", response_model=CaptureTokenOut)
def generate_patient_capture_token(
    patient_id: uuid.UUID,
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
) -> CaptureTokenOut:
    """Generate a signed, short-lived mobile selfie capture token for a patient."""
    patient = _get_authorized_patient(db, patient_id, clinician)
    token = create_capture_token(
        patient_id=patient.id,
        clinic_id=clinician.clinic_id,
        clinician_id=clinician.id,
        ttl_minutes=CAPTURE_TOKEN_DEFAULT_TTL_MINUTES,
    )
    return CaptureTokenOut(
        token=token,
        capture_path=f"/capture/{token}",
        expires_in_seconds=CAPTURE_TOKEN_DEFAULT_TTL_MINUTES * 60,
        patient_id=patient.id,
    )


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


@router.get("/{patient_id}/medications", response_model=PatientMedicationListResponse)
def get_patient_medications(
    patient_id: uuid.UUID,
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
) -> PatientMedicationListResponse:
    """Return all prescribed medications and active topicals for a patient."""
    patient = _get_authorized_patient(db, patient_id, clinician)
    stmt = (
        select(PatientMedication)
        .where(PatientMedication.patient_id == patient.id)
        .order_by(PatientMedication.start_date.desc(), PatientMedication.created_at.desc())
    )
    meds = list(db.execute(stmt).scalars().all())
    today = date.today()
    out_list: list[PatientMedicationOut] = []
    for m in meds:
        m_out = PatientMedicationOut.model_validate(m)
        m_out.is_active = m.end_date is None or m.end_date >= today
        out_list.append(m_out)

    return PatientMedicationListResponse(
        patient_id=patient.id,
        medications=out_list,
        total=len(out_list),
        disclaimer=CLINICAL_DISCLAIMER,
    )


@router.post(
    "/{patient_id}/medications",
    response_model=PatientMedicationOut,
    status_code=status.HTTP_201_CREATED,
)
def add_patient_medication(
    patient_id: uuid.UUID,
    payload: PatientMedicationCreate,
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
) -> PatientMedicationOut:
    """Record a new prescribed medication, topical, or active skincare regimen item."""
    patient = _get_authorized_patient(db, patient_id, clinician)
    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Medication name cannot be blank.",
        )

    med = PatientMedication(
        patient_id=patient.id,
        name=name,
        category=payload.category.strip() if payload.category else "other",
        dose=payload.dose.strip() if payload.dose else None,
        rxnorm_code=payload.rxnorm_code.strip() if payload.rxnorm_code else None,
        start_date=payload.start_date,
        end_date=payload.end_date,
        prescriber=payload.prescriber.strip() if payload.prescriber else clinician.full_name,
        notes=payload.notes.strip() if payload.notes else None,
    )
    db.add(med)
    db.commit()
    db.refresh(med)

    med_out = PatientMedicationOut.model_validate(med)
    med_out.is_active = med.end_date is None or med.end_date >= date.today()
    return med_out


@router.delete(
    "/{patient_id}/medications/{medication_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_patient_medication(
    patient_id: uuid.UUID,
    medication_id: uuid.UUID,
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
) -> None:
    """Delete a medication record from the patient chart."""
    patient = _get_authorized_patient(db, patient_id, clinician)
    med = db.get(PatientMedication, medication_id)
    if med is None or med.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication record not found.",
        )
    db.delete(med)
    db.commit()


@router.get(
    "/{patient_id}/medication-correlations",
    response_model=PatientMedicationCorrelationsResponse,
)
def get_patient_medication_correlations(
    patient_id: uuid.UUID,
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
) -> PatientMedicationCorrelationsResponse:
    """Cross-reference patient medications with longitudinal skin concern trajectories."""
    patient = _get_authorized_patient(db, patient_id, clinician)

    # 1. Fetch all medications sorted by start_date asc
    med_stmt = (
        select(PatientMedication)
        .where(PatientMedication.patient_id == patient.id)
        .order_by(PatientMedication.start_date.asc())
    )
    medications = list(db.execute(med_stmt).scalars().all())

    # 2. Fetch all successful visits with concern scores sorted by visit_date asc
    visit_stmt = (
        select(Visit)
        .where(Visit.patient_id == patient.id, Visit.youcam_status == "success")
        .options(selectinload(Visit.concern_scores))
        .order_by(Visit.visit_date.asc(), Visit.created_at.asc())
    )
    visits_db = list(db.execute(visit_stmt).scalars().all())

    visits_payload = []
    for v in visits_db:
        scores_dict = {cs.concern: cs.score for cs in v.concern_scores}
        visits_payload.append({
            "visit_date": v.visit_date,
            "scores": scores_dict,
        })

    correlations: list[MedicationCorrelationOut] = []
    active_count = 0
    today = date.today()

    for med in medications:
        if med.end_date is None or med.end_date >= today:
            active_count += 1

        corr_res = cross_reference_medication(
            medication_id=str(med.id),
            medication_name=med.name,
            category=med.category,
            dose=med.dose,
            start_date=med.start_date,
            end_date=med.end_date,
            visits=visits_payload,
        )

        responses_out = [
            ConcernResponseSummaryOut(
                concern=r.concern,
                label=r.label,
                baseline_score=r.baseline_score,
                latest_score=r.latest_score,
                delta=r.delta,
                pct_change=r.pct_change,
                mdc=r.mdc,
                direction=r.direction,
                is_improved=r.is_improved,
                is_worsened=r.is_worsened,
                exceeds_mdc=r.exceeds_mdc,
            )
            for r in corr_res.concern_responses
        ]

        correlations.append(
            MedicationCorrelationOut(
                medication_id=corr_res.medication_id,
                medication_name=corr_res.medication_name,
                category=corr_res.category,
                category_label=corr_res.category_label,
                dose=corr_res.dose,
                start_date=corr_res.start_date,
                end_date=corr_res.end_date,
                is_active=corr_res.is_active,
                days_on_therapy=corr_res.days_on_therapy,
                baseline_visit_date=corr_res.baseline_visit_date,
                latest_visit_date=corr_res.latest_visit_date,
                response_status=corr_res.response_status,
                headline=corr_res.headline,
                clinical_note=corr_res.clinical_note,
                concern_responses=responses_out,
            )
        )

    return PatientMedicationCorrelationsResponse(
        patient_id=patient.id,
        visit_count=len(visits_db),
        active_medications_count=active_count,
        correlations=correlations,
        disclaimer=CLINICAL_DISCLAIMER,
    )
