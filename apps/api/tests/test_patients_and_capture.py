"""Clinician patient directory and token-signed mobile patient capture flow tests."""

import io
from datetime import datetime, timedelta, timezone

import jwt
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


def test_patient_directory_and_creation(
    client: TestClient,
    migrated_db_session: Session,
) -> None:
    """Verify clinician can list, search, view, and create patients."""
    seed_demo_longitudinal(migrated_db_session)
    headers = _auth_headers(client)

    # List patients
    list_resp = client.get("/api/patients", headers=headers)
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["disclaimer"] == CLINICAL_DISCLAIMER
    assert len(data["patients"]) >= 1
    elena = next((p for p in data["patients"] if p["external_ref"] == "PT-DEMO-001"), None)
    assert elena is not None
    assert elena["visit_count"] >= 3
    assert elena["latest_visit_date"] == "2026-10-13"

    # Search patients
    search_resp = client.get("/api/patients?q=Rostova", headers=headers)
    assert search_resp.status_code == 200
    assert any(p["id"] == elena["id"] for p in search_resp.json()["patients"])

    # Create a new patient
    create_resp = client.post(
        "/api/patients",
        headers=headers,
        json={
            "full_name": "Marcus Vance",
            "external_ref": "PT-DEMO-002",
            "dob": "1988-11-03",
            "consent_version": "v1-2026-10",
            "notes": "Post-inflammatory hyperpigmentation follow-up.",
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["full_name"] == "Marcus Vance"
    assert created["visit_count"] == 0

    # Get patient detail
    detail_resp = client.get(f"/api/patients/{created['id']}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["external_ref"] == "PT-DEMO-002"


def test_capture_token_security_boundary(
    client: TestClient,
    migrated_db_session: Session,
) -> None:
    """Verify patient capture tokens cannot access clinician routes and expired tokens fail."""
    seed_info = seed_demo_longitudinal(migrated_db_session)
    headers = _auth_headers(client)
    patient_id = seed_info["patient_id"]
    settings = get_settings()

    cap_resp = client.post(
        f"/api/patients/{patient_id}/capture-token",
        headers=headers,
    )
    assert cap_resp.status_code == 200
    capture_token = cap_resp.json()["token"]
    assert cap_resp.json()["capture_path"] == f"/capture/{capture_token}"

    # Patient capture token MUST be rejected on clinician /api/me route
    me_attempt = client.get(
        "/api/me",
        headers={"Authorization": f"Bearer {capture_token}"},
    )
    assert me_attempt.status_code == 401

    # Expired capture token MUST be rejected on /api/capture/{token}
    expired_payload = {
        "sub": patient_id,
        "purpose": "patient_capture",
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    expired_token = jwt.encode(
        expired_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    exp_resp = client.get(f"/api/capture/{expired_token}")
    assert exp_resp.status_code == 401


def test_end_to_end_patient_capture_updates_clinician_dashboard(
    client: TestClient,
    migrated_db_session: Session,
) -> None:
    """Verify full flow: clinician generates link -> patient submits selfie -> visit #4 & PDF ready."""
    seed_demo_longitudinal(migrated_db_session)
    headers = _auth_headers(client)

    # Create an isolated patient to test capture flow
    create_resp = client.post(
        "/api/patients",
        headers=headers,
        json={
            "full_name": "Capture Flow Patient",
            "external_ref": "PT-CAP-001",
            "consent_version": "v1-2026-10",
        },
    )
    assert create_resp.status_code == 201
    patient_id = create_resp.json()["id"]

    # 1. Clinician generates signed capture token
    cap_resp = client.post(f"/api/patients/{patient_id}/capture-token", headers=headers)
    assert cap_resp.status_code == 200
    capture_token = cap_resp.json()["token"]

    # 2. Patient opens /api/capture/{token} (no clinician auth header required)
    session_resp = client.get(f"/api/capture/{capture_token}")
    assert session_resp.status_code == 200
    session_info = session_resp.json()
    assert session_info["patient_id"] == patient_id
    assert session_info["privacy_notice"] == "Photos are stored privately and deletable on request."
    assert session_info["disclaimer"] == CLINICAL_DISCLAIMER

    # 3. Patient submits visit 1 (baseline) and visit 2 (follow-up) via capture link
    fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    sub1 = client.post(
        f"/api/capture/{capture_token}/submit",
        data={
            "visit_date": "2026-02-01",
            "chief_complaint": "Initial cheek redness",
            "routine_text": "Gentle cleanser",
            "treatment_changes": "Start azelaic acid 15%",
        },
        files={"image": ("selfie1.jpg", io.BytesIO(fake_jpeg), "image/jpeg")},
    )
    assert sub1.status_code == 201
    assert sub1.json()["youcam_status"] == "success"
    assert len(sub1.json()["concern_scores"]) == 12

    sub2 = client.post(
        f"/api/capture/{capture_token}/submit",
        data={
            "visit_date": "2026-05-01",
            "chief_complaint": "90-day re-evaluation",
            "routine_text": "Gentle cleanser + azelaic acid 15%",
            "treatment_changes": "Maintain regimen",
        },
        files={"image": ("selfie2.jpg", io.BytesIO(fake_jpeg), "image/jpeg")},
    )
    assert sub2.status_code == 201

    # 4. Clinician dashboard endpoints immediately reflect 2 visits, trends, flags, and PDF
    visits_resp = client.get(f"/api/patients/{patient_id}/visits", headers=headers)
    assert visits_resp.status_code == 200
    assert visits_resp.json()["visit_count"] == 2

    trends_resp = client.get(f"/api/patients/{patient_id}/trends", headers=headers)
    assert trends_resp.status_code == 200
    assert len(trends_resp.json()["concerns"]) == 12

    pdf_resp = client.get(f"/api/patients/{patient_id}/report.pdf", headers=headers)
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"].startswith("application/pdf")
    assert CLINICAL_DISCLAIMER.encode("utf-8") in pdf_resp.content

