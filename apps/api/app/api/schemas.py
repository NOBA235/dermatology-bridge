"""Pydantic v2 schemas for Visit creation and responses."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict

from app import CLINICAL_DISCLAIMER


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
    """Full visit response returned by POST /api/visits."""

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
