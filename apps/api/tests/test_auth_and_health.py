"""Authentication, database migration, seed idempotency, and health check tests."""

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app import CLINICAL_DISCLAIMER
from app.config import Settings, get_settings, verify_startup_invariants
from app.db.models import (
    Clinic,
    Clinician,
    ConcernScore,
    Patient,
    TreatmentFlag,
    Visit,
)
from app.scripts.seed import seed_baseline


def test_health_returns_200_with_db_connectivity(client: TestClient) -> None:
    """Exit criterion 1: GET /health returns 200 with DB connectivity check."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["allow_live_calls"] is False
    assert body["disclaimer"] == CLINICAL_DISCLAIMER


def test_migration_applies_to_clean_db_in_one_command(
    migrated_db_session: Session,
) -> None:
    """Exit criterion 2: Migration applies to a clean DB in one command with all 6 tables."""
    bind = migrated_db_session.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    expected_tables = {
        "clinics",
        "clinicians",
        "patients",
        "visits",
        "concern_scores",
        "treatment_flags",
    }
    assert expected_tables.issubset(tables)


def test_seed_script_idempotent(migrated_db_session: Session) -> None:
    """Exit criterion 3: Seed script idempotent; running twice doesn't duplicate."""
    first = seed_baseline(migrated_db_session)
    second = seed_baseline(migrated_db_session)

    assert first == second

    clinic_count = migrated_db_session.scalar(select(func.count()).select_from(Clinic))
    clinician_count = migrated_db_session.scalar(
        select(func.count()).select_from(Clinician)
    )
    patient_count = migrated_db_session.scalar(select(func.count()).select_from(Patient))
    visit_count = migrated_db_session.scalar(select(func.count()).select_from(Visit))
    score_count = migrated_db_session.scalar(
        select(func.count()).select_from(ConcernScore)
    )
    flag_count = migrated_db_session.scalar(
        select(func.count()).select_from(TreatmentFlag)
    )

    assert clinic_count == 1
    assert clinician_count == 1
    assert patient_count == 1
    assert visit_count == 0
    assert score_count == 0
    assert flag_count == 0


def test_login_jwt_and_protected_route_enforcement(
    client: TestClient,
    migrated_db_session: Session,
) -> None:
    """Exit criterion 4: Login returns a JWT; protected route rejects without it and accepts with it."""
    seed_baseline(migrated_db_session)
    settings = get_settings()

    # Protected route rejects without Authorization header
    unauth_res = client.get("/api/me")
    assert unauth_res.status_code == 401

    # Protected route rejects malformed/invalid JWT
    bad_token_res = client.get(
        "/api/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert bad_token_res.status_code == 401

    # Login with wrong password fails
    bad_login_res = client.post(
        "/auth/login",
        json={
            "email": settings.SEED_CLINICIAN_EMAIL,
            "password": "wrong-password",
        },
    )
    assert bad_login_res.status_code == 401

    # Login with valid credentials returns JWT
    login_res = client.post(
        "/auth/login",
        json={
            "email": settings.SEED_CLINICIAN_EMAIL,
            "password": settings.SEED_CLINICIAN_PASSWORD,
        },
    )
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert token_data["token_type"] == "bearer"
    assert isinstance(token_data["access_token"], str)
    assert len(token_data["access_token"]) > 20
    assert token_data["clinician"]["email"] == settings.SEED_CLINICIAN_EMAIL

    # Protected route accepts valid JWT
    me_res = client.get(
        "/api/me",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == settings.SEED_CLINICIAN_EMAIL
    assert me_data["id"] == token_data["clinician"]["id"]


def test_allow_live_calls_default_and_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exit criterion 5: ALLOW_LIVE_CALLS=false is default, read correctly, and fails fast if invalid."""
    monkeypatch.delenv("ALLOW_LIVE_CALLS", raising=False)
    default_settings = Settings(_env_file=None)
    assert default_settings.ALLOW_LIVE_CALLS is False
    verify_startup_invariants(default_settings)

    # Explicit 'false' parses to False
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "false")
    explicit_false = Settings(_env_file=None)
    assert explicit_false.ALLOW_LIVE_CALLS is False

    # Empty string / unset value in env fails fast with ValidationError
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    # ALLOW_LIVE_CALLS=true without YOUCAM_API_KEY fails startup invariant
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "true")
    monkeypatch.setenv("YOUCAM_API_KEY", "")
    live_without_key = Settings(_env_file=None)
    with pytest.raises(RuntimeError, match="YOUCAM_API_KEY"):
        verify_startup_invariants(live_without_key)

