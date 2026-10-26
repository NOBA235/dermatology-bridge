"""Materialized treatment_flags computation and atomic delete-then-insert regeneration."""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app import CLINICAL_DISCLAIMER
from app.db.models import ConcernScore, TreatmentFlag, Visit
from app.domain.concerns import CONCERN_LIST
from app.domain.flags import compute_delta_and_pct, compute_verdict
from app.services.agent.narrate import AgentNarrativeOutput, generate_narrative
from app.services.agent.validate import ensure_clinical_disclaimer


@dataclass(frozen=True)
class FlagRegenerationResult:
    """Result of regenerating materialized treatment_flags for a patient."""

    patient_id: uuid.UUID
    visit_count: int
    top_concern_indices: list[int]
    top_concerns: list[str]
    summary: str
    used_fallback: bool
    flags: list[TreatmentFlag]


def build_agent_source_json(visits: list[Visit]) -> dict[str, Any]:
    """Build structured JSON input for the agent from visits and concern_scores (no images)."""
    visit_count = len(visits)
    if visit_count == 0:
        return {
            "visit_count": 0,
            "concerns": [],
            "complaint_texts": [],
            "treatment_changes": [],
        }

    baseline_visit = visits[0]
    latest_visit = visits[-1]
    days_between = (latest_visit.visit_date - baseline_visit.visit_date).days

    scores_map: dict[tuple[uuid.UUID, str], ConcernScore] = {}
    for visit in visits:
        for cs in visit.concern_scores:
            scores_map[(visit.id, cs.concern)] = cs

    concerns_payload: list[dict[str, Any]] = []
    for concern in CONCERN_LIST:
        points: list[dict[str, Any]] = []
        for visit in visits:
            cs_row = scores_map.get((visit.id, concern))
            if cs_row is not None:
                points.append(
                    {
                        "visit_id": str(visit.id),
                        "visit_date": visit.visit_date.isoformat(),
                        "score": str(cs_row.score),
                    }
                )

        base_cs = scores_map.get((baseline_visit.id, concern))
        latest_cs = scores_map.get((latest_visit.id, concern))
        base_score = base_cs.score if base_cs is not None else Decimal("0.00")
        latest_score = latest_cs.score if latest_cs is not None else Decimal("0.00")

        if visit_count < 2:
            delta = Decimal("0.00")
            pct_change: Decimal | None = Decimal("0.00")
        else:
            computed_delta, computed_pct = compute_delta_and_pct(base_score, latest_score)
            delta = computed_delta if computed_delta is not None else Decimal("0.00")
            pct_change = computed_pct

        verdict = compute_verdict(
            concern,
            base_score,
            latest_score,
            days_between=days_between,
            visit_count=visit_count,
        )

        concerns_payload.append(
            {
                "concern": concern,
                "baseline_score": str(base_score),
                "latest_score": str(latest_score),
                "delta": str(delta),
                "pct_change": str(pct_change) if pct_change is not None else None,
                "verdict": verdict,
                "points": points,
            }
        )

    complaint_texts = [v.chief_complaint for v in visits if v.chief_complaint]
    treatment_changes = [v.treatment_changes for v in visits if v.treatment_changes]

    return {
        "visit_count": visit_count,
        "days_between": days_between,
        "concerns": concerns_payload,
        "complaint_texts": complaint_texts,
        "treatment_changes": treatment_changes,
    }


def regenerate_patient_flags(
    db: Session,
    patient_id: uuid.UUID,
    *,
    llm_callable: Callable[[dict[str, Any], int], dict[str, Any] | str] | None = None,
) -> FlagRegenerationResult:
    """Atomically delete and re-insert all treatment_flags for a patient."""
    stmt = (
        select(Visit)
        .where(
            Visit.patient_id == patient_id,
            Visit.youcam_status == "success",
        )
        .options(selectinload(Visit.concern_scores))
        .order_by(Visit.visit_date.asc(), Visit.created_at.asc())
    )
    visits = list(db.execute(stmt).scalars().all())

    versions = {v.analysis_version for v in visits}
    if len(versions) > 1:
        raise ValueError(
            f"Cannot compute flags across visits with mismatched analysis_version: {sorted(versions)}"
        )

    # Atomic delete-then-insert per patient
    db.execute(delete(TreatmentFlag).where(TreatmentFlag.patient_id == patient_id))

    if not visits:
        db.commit()
        return FlagRegenerationResult(
            patient_id=patient_id,
            visit_count=0,
            top_concern_indices=[],
            top_concerns=[],
            summary=ensure_clinical_disclaimer(
                "No completed visits available for flag computation."
            ),
            used_fallback=False,
            flags=[],
        )

    source_json = build_agent_source_json(visits)
    narrative: AgentNarrativeOutput = generate_narrative(
        source_json,
        llm_callable=llm_callable,
    )

    baseline_visit = visits[0]
    latest_visit = visits[-1]
    concern_items = {
        item["concern"]: item for item in source_json["concerns"]
    }

    inserted_flags: list[TreatmentFlag] = []
    for concern in CONCERN_LIST:
        c_item = concern_items[concern]
        hyp_text = ensure_clinical_disclaimer(
            narrative.hypotheses.get(concern, CLINICAL_DISCLAIMER)
        )
        flag_row = TreatmentFlag(
            patient_id=patient_id,
            concern=concern,
            baseline_visit_id=baseline_visit.id,
            latest_visit_id=latest_visit.id,
            delta=Decimal(str(c_item["delta"])),
            pct_change=(
                Decimal(str(c_item["pct_change"]))
                if c_item.get("pct_change") is not None
                else None
            ),
            verdict=str(c_item["verdict"]),
            hypothesis=hyp_text,
        )
        db.add(flag_row)
        inserted_flags.append(flag_row)

    db.commit()
    for row in inserted_flags:
        db.refresh(row)

    top_concerns = [CONCERN_LIST[i] for i in narrative.top_concern_indices]
    return FlagRegenerationResult(
        patient_id=patient_id,
        visit_count=len(visits),
        top_concern_indices=narrative.top_concern_indices,
        top_concerns=top_concerns,
        summary=narrative.summary,
        used_fallback=narrative.used_fallback,
        flags=inserted_flags,
    )
