"""FHIR R4 Observation export for patient skin concern scores (GET /api/patients/{id}/fhir).

For clinician review — not a diagnosis.
"""

from datetime import datetime, timezone
from typing import Literal
import uuid

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import CLINICAL_DISCLAIMER
from app.db.models import Patient, Visit
from app.domain.concerns import CONCERN_DIRECTION, CONCERN_LABELS, CONCERN_LIST


class FHIRCoding(BaseModel):
    """FHIR Coding element."""

    model_config = ConfigDict(extra="forbid")

    system: str
    code: str
    display: str


class FHIRCodeableConcept(BaseModel):
    """FHIR CodeableConcept element."""

    model_config = ConfigDict(extra="forbid")

    coding: list[FHIRCoding]
    text: str | None = None


class FHIRReference(BaseModel):
    """FHIR Reference element."""

    model_config = ConfigDict(extra="forbid")

    reference: str
    display: str | None = None


class FHIRQuantity(BaseModel):
    """FHIR Quantity element for numeric 0..100 skin concern scores."""

    model_config = ConfigDict(extra="forbid")

    value: float
    unit: str = "score (0-100)"
    system: str = "http://unitsofmeasure.org"
    code: str = "{score}"


class FHIRAnnotation(BaseModel):
    """FHIR Annotation element carrying the mandatory clinical disclaimer."""

    model_config = ConfigDict(extra="forbid")

    text: str


class FHIRObservation(BaseModel):
    """FHIR R4 Observation resource representing a single concern_scores row."""

    model_config = ConfigDict(extra="forbid")

    resourceType: Literal["Observation"] = "Observation"
    id: str
    status: Literal["final", "preliminary", "amended"] = "final"
    category: list[FHIRCodeableConcept]
    code: FHIRCodeableConcept
    subject: FHIRReference
    encounter: FHIRReference
    effectiveDateTime: str
    valueQuantity: FHIRQuantity
    interpretation: list[FHIRCodeableConcept]
    note: list[FHIRAnnotation]


class FHIRBundleEntry(BaseModel):
    """Single entry in a FHIR Bundle."""

    model_config = ConfigDict(extra="forbid")

    fullUrl: str
    resource: FHIRObservation


class FHIRBundle(BaseModel):
    """FHIR R4 Bundle of Observation resources for a patient."""

    model_config = ConfigDict(extra="forbid")

    resourceType: Literal["Bundle"] = "Bundle"
    id: str
    type: Literal["collection"] = "collection"
    timestamp: str
    total: int
    entry: list[FHIRBundleEntry]


def build_patient_fhir_bundle(
    db: Session,
    patient_id: uuid.UUID,
) -> FHIRBundle:
    """Build a validated FHIR R4 Bundle of Observation resources for all concern_scores of a patient."""
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise ValueError(f"Patient {patient_id} not found.")

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
    concern_order = {c: idx for idx, c in enumerate(CONCERN_LIST)}

    entries: list[FHIRBundleEntry] = []
    for visit in visits:
        sorted_scores = sorted(
            visit.concern_scores,
            key=lambda cs: concern_order.get(cs.concern, 999),
        )
        for cs in sorted_scores:
            obs_id = f"obs-{visit.id}-{cs.concern}"
            label = CONCERN_LABELS.get(cs.concern, cs.concern)
            direction = CONCERN_DIRECTION.get(cs.concern, "lower_is_better")

            obs = FHIRObservation(
                id=obs_id,
                status="final",
                category=[
                    FHIRCodeableConcept(
                        coding=[
                            FHIRCoding(
                                system="http://terminology.hl7.org/CodeSystem/observation-category",
                                code="exam",
                                display="Exam",
                            )
                        ],
                        text="Dermatology Skin AI Assessment",
                    )
                ],
                code=FHIRCodeableConcept(
                    coding=[
                        FHIRCoding(
                            system="https://dermobridge.clinical/fhir/CodeSystem/youcam-skin-concern",
                            code=cs.concern,
                            display=label,
                        )
                    ],
                    text=label,
                ),
                subject=FHIRReference(
                    reference=f"Patient/{patient.id}",
                    display=patient.full_name,
                ),
                encounter=FHIRReference(
                    reference=f"Encounter/{visit.id}",
                    display=f"Clinic Visit {visit.visit_date.isoformat()}",
                ),
                effectiveDateTime=f"{visit.visit_date.isoformat()}T00:00:00Z",
                valueQuantity=FHIRQuantity(value=float(cs.score)),
                interpretation=[
                    FHIRCodeableConcept(
                        coding=[
                            FHIRCoding(
                                system="https://dermobridge.clinical/fhir/CodeSystem/severity-bucket",
                                code=cs.severity,
                                display=cs.severity.capitalize(),
                            )
                        ],
                        text=f"Severity bucket: {cs.severity} ({direction})",
                    )
                ],
                note=[FHIRAnnotation(text=CLINICAL_DISCLAIMER)],
            )
            entries.append(
                FHIRBundleEntry(
                    fullUrl=f"urn:uuid:{obs_id}",
                    resource=obs,
                )
            )

    return FHIRBundle(
        id=f"bundle-patient-{patient.id}",
        type="collection",
        timestamp=datetime.now(timezone.utc).isoformat(),
        total=len(entries),
        entry=entries,
    )
