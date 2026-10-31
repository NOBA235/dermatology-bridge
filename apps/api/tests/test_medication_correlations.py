"""Prescription cross-referencing and longitudinal treatment correlation tests.

For clinician review — not a diagnosis.
"""

from datetime import date
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import CLINICAL_DISCLAIMER
from app.config import get_settings
from app.scripts.seed import seed_demo_longitudinal


def _auth_headers(client: TestClient) -> dict[str, str]:
    settings = get_settings()
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


def test_medication_crud_endpoints(
    client: TestClient,
    migrated_db_session: Session,
) -> None:
    """Verify clinician can add, list, and delete medications for a patient."""
    seed_info = seed_demo_longitudinal(migrated_db_session)
    headers = _auth_headers(client)
    patient_id = seed_info["demo_patient_id"]

    # 1. List pre-seeded medications
    list_resp = client.get(f"/api/patients/{patient_id}/medications", headers=headers)
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["disclaimer"] == CLINICAL_DISCLAIMER
    assert data["total"] == 4
    med_names = [m["name"] for m in data["medications"]]
    assert "Adapalene 0.1% Gel" in med_names
    assert "Ceramide Barrier Cream" in med_names

    # 2. Add a new medication
    add_resp = client.post(
        f"/api/patients/{patient_id}/medications",
        headers=headers,
        json={
            "name": "Doxycycline Hyclate",
            "category": "oral_antibiotic",
            "dose": "100mg orally once daily with food",
            "rxnorm_code": "1650369",
            "start_date": "2026-10-15",
            "end_date": "2026-11-15",
            "notes": "Short 30-day anti-inflammatory bridge for papulopustular flare.",
        },
    )
    assert add_resp.status_code == 201
    created_med = add_resp.json()
    assert created_med["name"] == "Doxycycline Hyclate"
    assert created_med["category"] == "oral_antibiotic"
    med_id = created_med["id"]

    # Verify updated list has 5
    list_resp2 = client.get(f"/api/patients/{patient_id}/medications", headers=headers)
    assert list_resp2.json()["total"] == 5

    # 3. Delete the added medication
    del_resp = client.delete(
        f"/api/patients/{patient_id}/medications/{med_id}",
        headers=headers,
    )
    assert del_resp.status_code == 204

    # Verify back to 4
    list_resp3 = client.get(f"/api/patients/{patient_id}/medications", headers=headers)
    assert list_resp3.json()["total"] == 4


def test_medication_correlations_and_change_points(
    client: TestClient,
    migrated_db_session: Session,
) -> None:
    """Verify that medication start dates are correlated with longitudinal concern deltas."""
    seed_info = seed_demo_longitudinal(migrated_db_session)
    headers = _auth_headers(client)
    patient_id = seed_info["demo_patient_id"]

    corr_resp = client.get(
        f"/api/patients/{patient_id}/medication-correlations",
        headers=headers,
    )
    assert corr_resp.status_code == 200
    data = corr_resp.json()
    assert data["disclaimer"] == CLINICAL_DISCLAIMER
    assert data["visit_count"] == 3
    assert data["active_medications_count"] == 4
    assert len(data["correlations"]) == 4

    corrs_by_name = {c["medication_name"]: c for c in data["correlations"]}

    # 1. Adapalene 0.1% Gel: initiated 2026-07-15, 90d elapsed, Acne delta -30.00 pt (68.00 -> 38.00)
    adapalene = corrs_by_name["Adapalene 0.1% Gel"]
    assert adapalene["category"] == "topical_retinoid"
    assert adapalene["response_status"] == "clinically_responsive"
    assert adapalene["days_on_therapy"] >= 90
    acne_resp = next(r for r in adapalene["concern_responses"] if r["concern"] == "acne")
    assert Decimal(str(acne_resp["delta"])) == Decimal("-30.00")
    assert acne_resp["is_improved"] is True
    assert acne_resp["exceeds_mdc"] is True

    # 2. Ceramide Barrier Cream: initiated 2026-07-15, Moisture delta +29.00 pt (42.00 -> 71.00)
    ceramide = corrs_by_name["Ceramide Barrier Cream"]
    assert ceramide["category"] == "barrier_repair"
    assert ceramide["response_status"] == "clinically_responsive"
    moisture_resp = next(r for r in ceramide["concern_responses"] if r["concern"] == "moisture")
    assert Decimal(str(moisture_resp["delta"])) == Decimal("29.00")
    assert moisture_resp["is_improved"] is True
    assert moisture_resp["exceeds_mdc"] is True

    # 3. Glycolic Acid 10% Toner: added 2026-09-29 before visit 3
    # Check that concern responses are computed correctly
    glycolic = corrs_by_name["Glycolic Acid 10% Exfoliating Toner"]
    assert glycolic["category"] == "topical_acid"
    assert len(glycolic["concern_responses"]) > 0


def test_medication_authorization_boundary(
    client: TestClient,
    migrated_db_session: Session,
) -> None:
    """Verify unauthorized calls are rejected with 401."""
    seed_info = seed_demo_longitudinal(migrated_db_session)
    patient_id = seed_info["demo_patient_id"]

    unauth_list = client.get(f"/api/patients/{patient_id}/medications")
    assert unauth_list.status_code == 401

    unauth_corrs = client.get(f"/api/patients/{patient_id}/medication-correlations")
    assert unauth_corrs.status_code == 401

