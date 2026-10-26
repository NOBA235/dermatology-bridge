"""Pydantic v2 schemas for Visit creation, longitudinal visit listing, and trend responses."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict

from app import CLINICAL_DISCLAIMER
from app.domain.concerns import ConcernDirection, SeverityBucket
from app.domain.flags import Verdict


class ConcernScoreOut(BaseModel):
    """Single concern score persisted for a visit."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    visit_id: uuid.UUID
    concern: str
    score: Decimal
    severity: str
    mask_url: str | None = None
    mask_storage_key: str | None = None


class VisitOut(BaseModel):
    """Full visit response returned by POST /api/visits and GET /api/patients/{id}/visits."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    visit_date: date
    chief_complaint: str | None = None
    routine_text: str | None = None
    treatment_changes: str | None = None
    analysis_version: int
    image_storage_key: str
    youcam_file_id: str | None = None
    youcam_task_id: str | None = None
    youcam_status: str
    raw_result: dict[str, Any] | None = None
    concern_scores: list[ConcernScoreOut] = []
    created_at: datetime
    updated_at: datetime
    disclaimer: str = CLINICAL_DISCLAIMER


class PatientVisitsResponse(BaseModel):
    """List of visits with concern scores for a single patient."""

    patient_id: uuid.UUID
    visit_count: int
    visits: list[VisitOut]
    disclaimer: str = CLINICAL_DISCLAIMER


class TrendDataPointOut(BaseModel):
    """Single longitudinal score point for a concern across visits."""

    visit_id: uuid.UUID
    visit_date: date
    score: Decimal
    severity: SeverityBucket


class ConcernTrendOut(BaseModel):
    """Per-concern longitudinal series, delta vs baseline, severity bucket, and verdict."""

    concern: str
    label: str
    direction: ConcernDirection
    mdc: float
    baseline_score: Decimal | None = None
    baseline_severity: SeverityBucket | None = None
    latest_score: Decimal | None = None
    latest_severity: SeverityBucket | None = None
    delta: Decimal | None = None
    pct_change: Decimal | None = None
    verdict: Verdict
    points: list[TrendDataPointOut] = []


class PatientTrendsResponse(BaseModel):
    """Longitudinal trend comparison response for GET /api/patients/{id}/trends."""

    patient_id: uuid.UUID
    visit_count: int
    analysis_version: int | None = None
    baseline_visit_id: uuid.UUID | None = None
    latest_visit_id: uuid.UUID | None = None
    baseline_date: date | None = None
    latest_date: date | None = None
    days_between: int | None = None
    concerns: list[ConcernTrendOut]
    disclaimer: str = CLINICAL_DISCLAIMER


class TreatmentFlagOut(BaseModel):
    """Materialized treatment_flags row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: uuid.UUID
    concern: str
    baseline_visit_id: uuid.UUID
    latest_visit_id: uuid.UUID
    delta: Decimal
    pct_change: Decimal | None = None
    verdict: Verdict
    hypothesis: str | None = None
    generated_at: datetime


class PatientFlagsResponse(BaseModel):
    """Response returned by POST /api/patients/{id}/flags/regenerate and GET /api/patients/{id}/flags."""

    patient_id: uuid.UUID
    visit_count: int
    top_concern_indices: list[int]
    top_concerns: list[str]
    summary: str
    used_fallback: bool
    flags: list[TreatmentFlagOut]
    disclaimer: str = CLINICAL_DISCLAIMER
