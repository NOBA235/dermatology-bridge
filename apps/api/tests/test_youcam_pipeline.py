"""YouCam S2S v2.0 client, mock pipeline, unit budget ledger, and visit ingestion tests."""

import csv
import json
from pathlib import Path
from typing import Any
import uuid

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.visits import get_storage_service, get_youcam_service
from app.config import REPO_ROOT, Settings
from app.db.models import ConcernScore, Patient, Visit
from app.domain.concerns import (
    ANALYSIS_VERSION,
    CONCERN_DIRECTION,
    CONCERN_LABELS,
    CONCERN_LIST,
    score_to_severity,
)
from app.scripts.seed import seed_baseline
from app.services.storage import PrivateStorageService
from app.services.youcam import (
    LiveYouCamClient,
    MockYouCamClient,
    UnitBudgetLogger,
    YouCamTaskFailedError,
    YouCamTimeoutError,
    compute_backoff_delay,
    get_youcam_client,
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


def test_frozen_concern_list_and_direction_map() -> None:
    """Working agreement unit test: verify CONCERN_LIST (12 frozen actions) and CONCERN_DIRECTION."""
    assert len(CONCERN_LIST) == 12
    assert ANALYSIS_VERSION == 1
    assert set(CONCERN_DIRECTION.keys()) == set(CONCERN_LIST)
    assert set(CONCERN_LABELS.keys()) == set(CONCERN_LIST)

    # Verify direction-of-good: moisture is higher_is_better, acne is lower_is_better
    assert CONCERN_DIRECTION["moisture"] == "higher_is_better"
    assert CONCERN_DIRECTION["radiance"] == "higher_is_better"
    assert CONCERN_DIRECTION["firmness"] == "higher_is_better"
    assert CONCERN_DIRECTION["skin_tone"] == "higher_is_better"

    assert CONCERN_DIRECTION["acne"] == "lower_is_better"
    assert CONCERN_DIRECTION["wrinkle"] == "lower_is_better"
    assert CONCERN_DIRECTION["pores"] == "lower_is_better"
    assert CONCERN_DIRECTION["texture"] == "lower_is_better"
    assert CONCERN_DIRECTION["redness"] == "lower_is_better"
    assert CONCERN_DIRECTION["oiliness"] == "lower_is_better"
    assert CONCERN_DIRECTION["dark_circle_v2"] == "lower_is_better"
    assert CONCERN_DIRECTION["dark_spot"] == "lower_is_better"

    # Severity heuristic respects direction of good
    assert score_to_severity("acne", 15.0) == "clear"
    assert score_to_severity("acne", 80.0) == "severe"
    assert score_to_severity("moisture", 85.0) == "clear"
    assert score_to_severity("moisture", 20.0) == "severe"


def test_youcam_factory_respects_allow_live_calls(tmp_path: Path) -> None:
    """Verify factory chooses MockYouCamClient by default and LiveYouCamClient when ALLOW_LIVE_CALLS=true."""
    csv_path = tmp_path / "budget.csv"
    mock_settings = Settings(_env_file=None, ALLOW_LIVE_CALLS=False)
    client_mock = get_youcam_client(settings=mock_settings, budget_csv_path=csv_path)
    assert isinstance(client_mock, MockYouCamClient)

    live_settings = Settings(
        _env_file=None,
        ALLOW_LIVE_CALLS=True,
        YOUCAM_API_KEY="yc_live_test_key_123456",
    )
    client_live = get_youcam_client(settings=live_settings, budget_csv_path=csv_path)
    assert isinstance(client_live, LiveYouCamClient)


@pytest.mark.anyio
async def test_backoff_schedule_and_live_client_identical_downstream_shape(
    tmp_path: Path,
) -> None:
    """Exit criterion: backoff (2s -> 30s cap, 90s timeout) and identical downstream shape between live and mock."""
    delays = [compute_backoff_delay(i) for i in range(6)]
    assert delays == [2.0, 4.0, 8.0, 16.0, 30.0, 30.0]

    fixture_data = json.loads(
        (REPO_ROOT / "fixtures" / "skin_analysis_sample.json").read_text(encoding="utf-8")
    )
    poll_calls = 0
    recorded_sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal poll_calls
        if request.url.path == "/s2s/v2.0/file":
            return httpx.Response(
                200,
                json={"status": 200, "result": {"file_id": "yc_file_live_001"}},
            )
        if request.url.path == "/s2s/v2.0/task/skin-analysis":
            return httpx.Response(
                200,
                json={"status": 200, "result": {"task_id": "yc_task_live_001"}},
            )
        if request.url.path == "/s2s/v2.0/task/skin-analysis/yc_task_live_001":
            poll_calls += 1
            if poll_calls < 3:
                return httpx.Response(
                    200,
                    json={
                        "status": 200,
                        "result": {
                            "task_id": "yc_task_live_001",
                            "task_status": "running",
                        },
                    },
                )
            return httpx.Response(200, json=fixture_data)
        return httpx.Response(404)

    async def fake_sleep(seconds: float) -> None:
        recorded_sleeps.append(seconds)

    transport = httpx.MockTransport(handler)
    budget_csv = tmp_path / "unit_budget.csv"
    budget_logger = UnitBudgetLogger(csv_path=budget_csv)

    async with httpx.AsyncClient(transport=transport) as http_client:
        live_client = LiveYouCamClient(
            base_url="https://yce-api-01.perfectcorp.com",
            api_key="test_key",
            budget_logger=budget_logger,
            http_client=http_client,
            sleep_fn=fake_sleep,
        )
        live_outcome = await live_client.analyze_image(b"fake-jpeg-bytes")

    mock_client = MockYouCamClient(budget_logger=budget_logger)
    mock_outcome = await mock_client.analyze_image(b"fake-jpeg-bytes")

    # Verify exponential backoff was used while task_status was 'running'
    assert recorded_sleeps == [2.0, 4.0]
    assert len(live_outcome.concern_scores) == 12
    assert len(mock_outcome.concern_scores) == 12

    # Identical downstream shape and values between live payload and mock mode
    assert [
        (c.concern, c.score, c.severity) for c in live_outcome.concern_scores
    ] == [
        (c.concern, c.score, c.severity) for c in mock_outcome.concern_scores
    ]


@pytest.mark.anyio
async def test_live_client_timeout_enforcement(tmp_path: Path) -> None:
    """Verify poll_task raises YouCamTimeoutError when 90s timeout is exceeded."""
    current_time = 0.0

    def fake_clock() -> float:
        return current_time

    async def fake_sleep(seconds: float) -> None:
        nonlocal current_time
        current_time += seconds

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": 200, "result": {"task_id": "t_slow", "task_status": "running"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        live_client = LiveYouCamClient(
            base_url="https://yce-api-01.perfectcorp.com",
            api_key="test_key",
            budget_logger=UnitBudgetLogger(csv_path=tmp_path / "timeout_budget.csv"),
            http_client=http_client,
            sleep_fn=fake_sleep,
            clock_fn=fake_clock,
            poll_timeout_seconds=90.0,
        )
        with pytest.raises(YouCamTimeoutError):
            await live_client.poll_task("t_slow")


def test_post_visits_pipeline_and_unit_budget_csv(
    client: TestClient,
    migrated_db_session: Session,
    tmp_path: Path,
) -> None:
    """Exit criteria 1, 2, 3, 4: Full POST /api/visits flow in mock mode + 12 concern_scores + CSV arithmetic."""
    seed_summary = seed_baseline(migrated_db_session)
    patient_id = seed_summary["patient_id"]
    settings = Settings(_env_file=None)

    budget_csv = tmp_path / "unit_budget.csv"
    storage_dir = tmp_path / "private_storage"
    mock_youcam = MockYouCamClient(budget_logger=UnitBudgetLogger(csv_path=budget_csv))
    storage_svc = PrivateStorageService(root_dir=storage_dir)

    client.app.dependency_overrides[get_youcam_service] = lambda: mock_youcam  # type: ignore[union-attr]
    client.app.dependency_overrides[get_storage_service] = lambda: storage_svc  # type: ignore[union-attr]

    headers = _auth_headers(client, settings)

    # First visit upload
    response = client.post(
        "/api/visits",
        headers=headers,
        data={
            "patient_id": patient_id,
            "visit_date": "2026-10-01",
            "chief_complaint": "Inflammatory acne on cheeks",
            "routine_text": "Gentle cleanser + SPF 50",
            "treatment_changes": "Started adapalene 0.1% nightly",
        },
        files={"image": ("selfie_v1.jpg", b"\xff\xd8\xff\xe0synthetic-selfie-1", "image/jpeg")},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()

    assert body["patient_id"] == patient_id
    assert body["youcam_status"] == "success"
    assert body["analysis_version"] == ANALYSIS_VERSION
    assert body["raw_result"] is not None
    assert body["raw_result"]["result"]["task_status"] == "success"
    assert "://" not in body["image_storage_key"]
    assert len(body["concern_scores"]) == 12

    returned_concerns = [cs["concern"] for cs in body["concern_scores"]]
    assert tuple(returned_concerns) == CONCERN_LIST
    for cs in body["concern_scores"]:
        assert cs["mask_url"] is not None
        assert cs["mask_storage_key"] is not None
        assert "://" not in cs["mask_storage_key"]
        assert (storage_dir / cs["mask_storage_key"]).exists()

    # Verify DB persistence in visits and concern_scores
    visit_id = uuid.UUID(body["id"])
    visit_row = migrated_db_session.execute(
        select(Visit).where(Visit.id == visit_id)
    ).scalar_one()
    assert visit_row.youcam_status == "success"
    assert visit_row.raw_result is not None

    score_rows = (
        migrated_db_session.execute(
            select(ConcernScore).where(ConcernScore.visit_id == visit_row.id)
        )
        .scalars()
        .all()
    )
    assert len(score_rows) == 12

    # Second visit to verify cumulative arithmetic in unit_budget.csv
    response_2 = client.post(
        "/api/visits",
        headers=headers,
        data={
            "patient_id": patient_id,
            "visit_date": "2026-10-24",
            "chief_complaint": "Follow-up visit",
        },
        files={"image": ("selfie_v2.jpg", b"\xff\xd8\xff\xe0synthetic-selfie-2", "image/jpeg")},
    )
    assert response_2.status_code == 201

    with budget_csv.open("r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 2
    assert int(rows[0]["actions_count"]) == 12
    assert int(rows[0]["cumulative_units"]) == 12
    assert int(rows[0]["remaining_budget"]) == 988

    assert int(rows[1]["actions_count"]) == 12
    assert int(rows[1]["cumulative_units"]) == 24
    assert int(rows[1]["remaining_budget"]) == 976


def test_post_visits_failure_path_sets_failed_status(
    client: TestClient,
    migrated_db_session: Session,
    tmp_path: Path,
) -> None:
    """Exit criterion 5: A failed task sets youcam_status='failed' and surfaces a clean error to the caller."""
    seed_summary = seed_baseline(migrated_db_session)
    patient_id = seed_summary["patient_id"]
    settings = Settings(_env_file=None)

    budget_csv = tmp_path / "fail_budget.csv"
    storage_dir = tmp_path / "fail_storage"
    failing_youcam = MockYouCamClient(
        budget_logger=UnitBudgetLogger(csv_path=budget_csv),
        simulate_failure=True,
    )
    storage_svc = PrivateStorageService(root_dir=storage_dir)

    client.app.dependency_overrides[get_youcam_service] = lambda: failing_youcam  # type: ignore[union-attr]
    client.app.dependency_overrides[get_storage_service] = lambda: storage_svc  # type: ignore[union-attr]

    headers = _auth_headers(client, settings)
    response = client.post(
        "/api/visits",
        headers=headers,
        data={
            "patient_id": patient_id,
            "visit_date": "2026-10-15",
            "chief_complaint": "Dark spots check",
        },
        files={"image": ("fail_selfie.jpg", b"SIMULATE_YOUCAM_FAILURE", "image/jpeg")},
    )

    assert response.status_code == 502
    err_body = response.json()
    assert err_body["youcam_status"] == "failed"
    assert "lighting" in err_body["detail"] or "Unable to complete" in err_body["detail"]
    failed_visit_id = uuid.UUID(err_body["visit_id"])

    # Verify DB row has youcam_status='failed' and 0 concern_scores
    visit_row = migrated_db_session.execute(
        select(Visit).where(Visit.id == failed_visit_id)
    ).scalar_one()
    assert visit_row.youcam_status == "failed"
    assert visit_row.raw_result is not None
    assert visit_row.raw_result["result"]["task_status"] == "error"

    score_rows = (
        migrated_db_session.execute(
            select(ConcernScore).where(ConcernScore.visit_id == visit_row.id)
        )
        .scalars()
        .all()
    )
    assert len(score_rows) == 0


def test_api_contract_doc_committed_and_verified() -> None:
    """Exit criterion 6: docs/api-contract.md committed with verified field names."""
    contract_path = REPO_ROOT / "docs" / "api-contract.md"
    assert contract_path.exists()
    content = contract_path.read_text(encoding="utf-8")
    assert "/s2s/v2.0/file" in content
    assert "/s2s/v2.0/task/skin-analysis" in content
    assert "result.file_id" in content
    assert "result.task_status" in content
    assert "result.results[]" in content
    for concern in CONCERN_LIST:
        assert concern in content
