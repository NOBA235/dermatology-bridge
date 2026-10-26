"""Phase 3 exit criteria and unit tests for flags prioritization, agent narration, and grounding validation."""

from typing import Any
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import CLINICAL_DISCLAIMER
from app.config import Settings
from app.db.models import TreatmentFlag, Visit
from app.domain.concerns import CONCERN_LIST
from app.scripts.seed import seed_demo_longitudinal
from app.services.agent import (
    AgentNarrativeOutput,
    UngroundedClaim,
    build_agent_source_json,
    collect_source_numbers,
    extract_numeric_tokens,
    generate_narrative,
    prioritize_concerns,
    validate_agent_output,
)


def _auth_headers(client: TestClient, settings: Settings) -> dict[str, str]:
    resp = client.post(
        "/auth/login",
        json={
            "email": settings.SEED_CLINICIAN_EMAIL,
            "password": settings.SEED_CLINICIAN_PASSWORD,
        },
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_prioritize_concerns_returns_top_3_indices_only() -> None:
    """Verify prioritize.py selects top 3 concerns by |delta| * complaint_relevance and returns indices only."""
    deltas = {c: 2.0 for c in CONCERN_LIST}
    deltas["acne"] = -30.0        # idx 0
    deltas["moisture"] = 29.0     # idx 6
    deltas["dark_spot"] = 19.0    # idx 10
    deltas["redness"] = -21.0     # idx 4

    # Mention dark_spot in complaint so 19.0 * 1.5 = 28.5 beats redness 21.0 * 1.0 = 21.0
    indices = prioritize_concerns(
        deltas,
        complaint_texts=["New hyperpigmentation dark spot on malar cheeks"],
        top_k=3,
    )
    assert isinstance(indices, list)
    assert len(indices) == 3
    assert all(isinstance(i, int) and 0 <= i < len(CONCERN_LIST) for i in indices)

    top_names = [CONCERN_LIST[i] for i in indices]
    assert "acne" in top_names
    assert "moisture" in top_names
    assert "dark_spot" in top_names


def test_validator_rejects_deliberately_hallucinated_number_and_triggers_fallback(
    migrated_db_session: Session,
) -> None:
    """Exit criterion 2 & unit test: Feed a deliberately hallucinated number -> validator rejects and fallback triggers."""
    seed_info = seed_demo_longitudinal(migrated_db_session)
    demo_patient_id = uuid.UUID(seed_info["demo_patient_id"])

    visits = list(
        migrated_db_session.execute(
            select(Visit)
            .where(Visit.patient_id == demo_patient_id)
            .options(selectinload(Visit.concern_scores))
            .order_by(Visit.visit_date.asc())
        )
        .scalars()
        .all()
    )
    source_json = build_agent_source_json(visits)

    # 1. Direct validator check with a hallucinated number (99.4 is nowhere in concern_scores)
    hallucinated_payload = {
        "summary": f"Acne improved from baseline 99.4 to 38.00. {CLINICAL_DISCLAIMER}",
        "top_concern_indices": [0, 6, 10],
        "hypotheses": {
            c: f"Score changed to 38.00. {CLINICAL_DISCLAIMER}" for c in CONCERN_LIST
        },
        "used_fallback": False,
        "disclaimer": CLINICAL_DISCLAIMER,
    }
    with pytest.raises(UngroundedClaim) as exc_info:
        validate_agent_output(hallucinated_payload, source_json)
    assert exc_info.value.ungrounded_value == pytest.approx(99.4)

    # 2. Caller regenerates once, then falls back to templates/narrative_fallback.md
    call_attempts: list[int] = []

    def always_hallucinating_llm(_src: dict[str, Any], attempt: int) -> dict[str, Any]:
        call_attempts.append(attempt)
        return hallucinated_payload

    fallback_result = generate_narrative(
        source_json,
        llm_callable=always_hallucinating_llm,
    )
    assert call_attempts == [0, 1]  # Initial attempt + 1 regeneration retry
    assert fallback_result.used_fallback is True
    # Fallback output itself must pass grounding validation
    validate_agent_output(fallback_result, source_json)

    # 3. If attempt 0 hallucinates but attempt 1 succeeds, retry recovers without fallback
    retry_attempts: list[int] = []

    def recover_on_retry_llm(src: dict[str, Any], attempt: int) -> dict[str, Any]:
        retry_attempts.append(attempt)
        if attempt == 0:
            return hallucinated_payload
        return generate_narrative(src).model_dump()

    recovered_result = generate_narrative(
        source_json,
        llm_callable=recover_on_retry_llm,
    )
    assert retry_attempts == [0, 1]
    assert recovered_result.used_fallback is False
    validate_agent_output(recovered_result, source_json)


def test_every_numeric_claim_traces_to_concern_scores_and_disclaimers_present(
    client: TestClient,
    migrated_db_session: Session,
) -> None:
    """Exit criteria 1, 3, 5: Every numeric claim traces to concern_scores, attribution hypothesis appears, disclaimers appended."""
    seed_info = seed_demo_longitudinal(migrated_db_session)
    demo_patient_id = seed_info["demo_patient_id"]
    settings = Settings(_env_file=None)
    headers = _auth_headers(client, settings)

    # Call POST /api/patients/{id}/flags/regenerate twice to verify idempotency
    res_1 = client.post(
        f"/api/patients/{demo_patient_id}/flags/regenerate",
        headers=headers,
    )
    assert res_1.status_code == 200
    res_2 = client.post(
        f"/api/patients/{demo_patient_id}/flags/regenerate",
        headers=headers,
    )
    assert res_2.status_code == 200
    body = res_2.json()

    # Verify delete-then-insert left exactly 12 flags in DB
    flag_count = migrated_db_session.scalar(
        select(func.count())
        .select_from(TreatmentFlag)
        .where(TreatmentFlag.patient_id == uuid.UUID(demo_patient_id))
    )
    assert flag_count == 12
    assert len(body["flags"]) == 12
    assert len(body["top_concern_indices"]) == 3
    assert len(body["top_concerns"]) == 3

    # Build grounded source numbers directly from the patient's Visits & ConcernScores
    visits = list(
        migrated_db_session.execute(
            select(Visit)
            .where(Visit.patient_id == uuid.UUID(demo_patient_id))
            .options(selectinload(Visit.concern_scores))
            .order_by(Visit.visit_date.asc())
        )
        .scalars()
        .all()
    )
    source_json = build_agent_source_json(visits)
    grounded_numbers = collect_source_numbers(source_json)

    # Verify every numeric token in summary traces to concern_scores within ±0.5
    summary_tokens = extract_numeric_tokens(body["summary"])
    assert len(summary_tokens) > 0
    for token in summary_tokens:
        assert any(
            abs(token - ref) <= 0.5 or abs(abs(token) - abs(ref)) <= 0.5
            for ref in grounded_numbers
        ), f"Summary token {token} not in {grounded_numbers}"

    # Verify every flag hypothesis traces to concern_scores and ends with clinical disclaimer
    flags_by_concern = {f["concern"]: f for f in body["flags"]}
    for concern in CONCERN_LIST:
        flag = flags_by_concern[concern]
        hyp = flag["hypothesis"]
        assert isinstance(hyp, str) and len(hyp) > 0
        assert hyp.endswith(CLINICAL_DISCLAIMER)

        hyp_tokens = extract_numeric_tokens(hyp)
        assert len(hyp_tokens) >= 2
        for token in hyp_tokens:
            assert any(
                abs(token - ref) <= 0.5 or abs(abs(token) - abs(ref)) <= 0.5
                for ref in grounded_numbers
            ), f"Hypothesis token {token} for {concern} not in {grounded_numbers}"

    # Exit criterion 3: Attribution hypothesis appears when treatment_changes mentions a recent product
    dark_spot_hyp = flags_by_concern["dark_spot"]["hypothesis"].lower()
    assert "glycolic" in dark_spot_hyp or "spf" in dark_spot_hyp
    assert "temporally associated" in dark_spot_hyp or "hypothesis" in dark_spot_hyp


def test_agent_output_passes_pydantic_schema_on_10_consecutive_runs(
    migrated_db_session: Session,
) -> None:
    """Exit criterion 4: Agent output passes Pydantic schema validation on 10 consecutive runs (no flaky JSON)."""
    seed_info = seed_demo_longitudinal(migrated_db_session)
    demo_patient_id = uuid.UUID(seed_info["demo_patient_id"])

    visits = list(
        migrated_db_session.execute(
            select(Visit)
            .where(Visit.patient_id == demo_patient_id)
            .options(selectinload(Visit.concern_scores))
            .order_by(Visit.visit_date.asc())
        )
        .scalars()
        .all()
    )
    source_json = build_agent_source_json(visits)

    for _run in range(10):
        output = generate_narrative(source_json)
        validated = AgentNarrativeOutput.model_validate(output.model_dump())
        assert validated.used_fallback is False
        assert len(validated.top_concern_indices) == 3
        assert set(validated.hypotheses.keys()) == set(CONCERN_LIST)
        for hyp in validated.hypotheses.values():
            assert hyp.endswith(CLINICAL_DISCLAIMER)
        validate_agent_output(validated, source_json)
