"""Longitudinal visit history, trend series, MDC verdict rules, and demo seed tests."""

from datetime import date
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import ConcernScore, Visit
from app.domain.concerns import ANALYSIS_VERSION, CONCERN_LIST
from app.domain.flags import MDC_TABLE, MIN_DAYS_BETWEEN, MIN_VISITS, compute_verdict
from app.domain.severity import map_score_to_severity
from app.scripts.seed import seed_demo_longitudinal, seed_baseline


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


def test_compute_verdict_insufficient_data_for_10_day_gap() -> None:
    """Exit criterion 2: compute_verdict returns insufficient_data for a 10-day gap."""
    assert MIN_DAYS_BETWEEN == 21
    assert MIN_VISITS == 2

    # 10-day gap (< 21 days) must return insufficient_data even with large delta
    verdict = compute_verdict("acne", 70.0, 35.0, days_between=10, visit_count=2)
    assert verdict == "insufficient_data"

    # Single visit (< MIN_VISITS) must also return insufficient_data
    verdict_single = compute_verdict("moisture", 40.0, 80.0, days_between=30, visit_count=1)
    assert verdict_single == "insufficient_data"


def test_compute_verdict_stalled_when_abs_delta_below_mdc() -> None:
    """Exit criterion 3: compute_verdict returns stalled when |delta| < MDC."""
    for concern in CONCERN_LIST:
        mdc = MDC_TABLE[concern]
        small_shift = mdc - 0.5
        assert compute_verdict(
            concern,
            50.0,
            50.0 + small_shift,
            days_between=30,
            visit_count=2,
        ) == "stalled"
        assert compute_verdict(
            concern,
            50.0,
            50.0 - small_shift,
            days_between=30,
            visit_count=2,
        ) == "stalled"


def test_compute_verdict_direction_of_good_moisture_vs_acne() -> None:
    """Exit criterion 4: Rising moisture returns improving; rising acne returns worsening."""
    # Rising moisture (42 -> 71, delta = +29 >= MDC 5.0) -> improving
    assert (
        compute_verdict("moisture", 42.0, 71.0, days_between=45, visit_count=2)
        == "improving"
    )
    # Falling moisture (71 -> 42, delta = -29) -> worsening
    assert (
        compute_verdict("moisture", 71.0, 42.0, days_between=45, visit_count=2)
        == "worsening"
    )

    # Rising acne (38 -> 68, delta = +30 >= MDC 5.0) -> worsening
    assert (
        compute_verdict("acne", 38.0, 68.0, days_between=45, visit_count=2)
        == "worsening"
    )
    # Falling acne (68 -> 38, delta = -30) -> improving
    assert (
        compute_verdict("acne", 68.0, 38.0, days_between=45, visit_count=2)
        == "improving"
    )


def test_seeded_patient_returns_3_visits_and_correct_deltas(
    client: TestClient,
    migrated_db_session: Session,
) -> None:
    """Exit criterion 1: Seeded patient returns 3 visits and correct per-concern deltas."""
    first_seed = seed_demo_longitudinal(migrated_db_session)
    second_seed = seed_demo_longitudinal(migrated_db_session)
    assert first_seed == second_seed

    demo_patient_id = first_seed["demo_patient_id"]
    settings = Settings(_env_file=None)
    headers = _auth_headers(client, settings)

    # 1. GET /api/patients/{id}/visits
    visits_res = client.get(f"/api/patients/{demo_patient_id}/visits", headers=headers)
    assert visits_res.status_code == 200
    visits_body = visits_res.json()
    assert visits_body["patient_id"] == demo_patient_id
    assert visits_body["visit_count"] == 3
    assert len(visits_body["visits"]) == 3
    for v in visits_body["visits"]:
        assert len(v["concern_scores"]) == 12
        assert v["youcam_status"] == "success"

    # 2. GET /api/patients/{id}/trends
    trends_res = client.get(f"/api/patients/{demo_patient_id}/trends", headers=headers)
    assert trends_res.status_code == 200
    trends_body = trends_res.json()
    assert trends_body["patient_id"] == demo_patient_id
    assert trends_body["visit_count"] == 3
    assert trends_body["days_between"] == 90
    assert trends_body["analysis_version"] == ANALYSIS_VERSION
    assert len(trends_body["concerns"]) == 12

    by_concern = {item["concern"]: item for item in trends_body["concerns"]}

    # Verify improving concerns (acne: 68 -> 38, delta -30.00; moisture: 42 -> 71, delta +29.00)
    acne_trend = by_concern["acne"]
    assert Decimal(acne_trend["baseline_score"]) == Decimal("68.00")
    assert Decimal(acne_trend["latest_score"]) == Decimal("38.00")
    assert Decimal(acne_trend["delta"]) == Decimal("-30.00")
    assert acne_trend["verdict"] == "improving"
    assert len(acne_trend["points"]) == 3

    moisture_trend = by_concern["moisture"]
    assert Decimal(moisture_trend["baseline_score"]) == Decimal("42.00")
    assert Decimal(moisture_trend["latest_score"]) == Decimal("71.00")
    assert Decimal(moisture_trend["delta"]) == Decimal("29.00")
    assert moisture_trend["verdict"] == "improving"
    assert len(moisture_trend["points"]) == 3

    # Verify stalled concern (wrinkle: 31.00 -> 29.50, delta -1.50, |delta| < MDC 4.0)
    wrinkle_trend = by_concern["wrinkle"]
    assert Decimal(wrinkle_trend["delta"]) == Decimal("-1.50")
    assert wrinkle_trend["verdict"] == "stalled"

    # Verify worsening concern (dark_spot: 32.00 -> 51.00, delta +19.00)
    dark_spot_trend = by_concern["dark_spot"]
    assert Decimal(dark_spot_trend["delta"]) == Decimal("19.00")
    assert dark_spot_trend["verdict"] == "worsening"


def test_trends_endpoint_survives_single_visit_patient(
    client: TestClient,
    migrated_db_session: Session,
) -> None:
    """Exit criterion 5: Trends endpoint survives a patient with only 1 visit (returns nulls, no crash)."""
    seed_info = seed_baseline(migrated_db_session)
    patient_id = uuid.UUID(seed_info["patient_id"])
    settings = Settings(_env_file=None)
    headers = _auth_headers(client, settings)

    # Insert exactly 1 visit for PT-0001
    single_visit = Visit(
        patient_id=patient_id,
        visit_date=date(2026, 10, 1),
        chief_complaint="Initial baseline scan",
        analysis_version=ANALYSIS_VERSION,
        image_storage_key=f"patients/{patient_id}/visits/v1/selfie.jpg",
        youcam_status="success",
        raw_result={"status": 200, "result": {"task_status": "success", "results": []}},
    )
    migrated_db_session.add(single_visit)
    migrated_db_session.flush()

    for concern in CONCERN_LIST:
        migrated_db_session.add(
            ConcernScore(
                visit_id=single_visit.id,
                concern=concern,
                score=Decimal("50.00"),
                severity=map_score_to_severity(concern, Decimal("50.00")),
            )
        )
    migrated_db_session.commit()

    res = client.get(f"/api/patients/{patient_id}/trends", headers=headers)
    assert res.status_code == 200
    body = res.json()

    assert body["visit_count"] == 1
    assert body["baseline_visit_id"] == str(single_visit.id)
    assert body["latest_visit_id"] is None
    assert body["days_between"] is None
    assert len(body["concerns"]) == 12

    for item in body["concerns"]:
        assert Decimal(item["baseline_score"]) == Decimal("50.00")
        assert item["latest_score"] is None
        assert item["delta"] is None
        assert item["pct_change"] is None
        assert item["verdict"] == "insufficient_data"
        assert len(item["points"]) == 1


def test_trends_endpoint_rejects_mismatched_analysis_version(
    client: TestClient,
    migrated_db_session: Session,
) -> None:
    """Verify belt-and-braces invariant: visits with different analysis_version cannot be trended."""
    seed_info = seed_baseline(migrated_db_session)
    patient_id = uuid.UUID(seed_info["patient_id"])
    settings = Settings(_env_file=None)
    headers = _auth_headers(client, settings)

    v1 = Visit(
        patient_id=patient_id,
        visit_date=date(2026, 8, 1),
        analysis_version=1,
        image_storage_key="patients/p/v1/selfie.jpg",
        youcam_status="success",
    )
    v2 = Visit(
        patient_id=patient_id,
        visit_date=date(2026, 9, 15),
        analysis_version=2,
        image_storage_key="patients/p/v2/selfie.jpg",
        youcam_status="success",
    )
    migrated_db_session.add_all([v1, v2])
    migrated_db_session.commit()

    res = client.get(f"/api/patients/{patient_id}/trends", headers=headers)
    assert res.status_code == 409
    assert "analysis_version" in res.json()["detail"]

