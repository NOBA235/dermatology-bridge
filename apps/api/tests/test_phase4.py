"""Phase 4 exit criteria tests for the 3-page A4 PDF report and FHIR Observation export."""

import re
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app import CLINICAL_DISCLAIMER
from app.config import Settings
from app.db.models import ConcernScore
from app.domain.concerns import CONCERN_LIST
from app.scripts.seed import seed_demo_longitudinal
from app.services.report import (
    FHIRBundle,
    FHIRObservation,
    build_patient_report_pdf,
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


def test_pdf_report_3_a4_pages_snapshot_sparklines_top3_and_greppable_disclaimer(
    client: TestClient,
    migrated_db_session: Session,
) -> None:
    """Exit criteria 1, 2, 3, 4, 5, 8: 3 A4 pages, 12 colour-coded concerns, 3-point sparklines, top-3 match, greppable disclaimer."""
    seed_info = seed_demo_longitudinal(migrated_db_session)
    demo_patient_id = seed_info["demo_patient_id"]
    settings = Settings(_env_file=None)
    headers = _auth_headers(client, settings)

    # Unauthenticated request must be rejected
    unauth = client.get(f"/api/patients/{demo_patient_id}/report.pdf")
    assert unauth.status_code == 401

    # Authenticated request returns application/pdf
    res = client.get(
        f"/api/patients/{demo_patient_id}/report.pdf",
        headers=headers,
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    pdf_bytes = res.content

    # Valid PDF header & trailer (opens cleanly in Chrome, Preview, Acrobat)
    assert pdf_bytes.startswith(b"%PDF-1.")
    assert b"%%EOF" in pdf_bytes[-64:]

    # Exit criterion 1: Exactly 3 A4 pages (595.28 x 841.89 pt)
    page_matches = re.findall(rb"/Type\s*/Page\b", pdf_bytes)
    assert len(page_matches) == 3
    assert b"/Count 3" in pdf_bytes
    assert b"595.28 841.89" in pdf_bytes

    # Exit criterion 5: Disclaimer string present and greppable in PDF bytes
    assert CLINICAL_DISCLAIMER.encode("utf-8") in pdf_bytes
    assert b"HYPOTHESIS" in pdf_bytes

    # Inspect rendered HTML & structured context
    _pdf, html_str, ctx = build_patient_report_pdf(
        migrated_db_session,
        uuid.UUID(demo_patient_id),
    )

    # Exit criterion 2: All 12 concerns appear in the snapshot grid with colour coding
    assert len(ctx["snapshot_rows"]) == 12
    for concern in CONCERN_LIST:
        assert f'data-concern="{concern}"' in html_str
    assert "severity-clear" in html_str or "severity-mild" in html_str
    assert "severity-moderate" in html_str
    assert "verdict-improving" in html_str
    assert "verdict-stalled" in html_str
    assert "verdict-worsening" in html_str

    # Exit criterion 3: Sparklines show 3 data points where 3 visits exist
    for row in ctx["snapshot_rows"]:
        assert row["points_count"] == 3
        assert row["sparkline_data_uri"].startswith("data:image/png;base64,")
    assert html_str.count('data-points-count="3"') == 12

    # Exit criterion 4: Top-3 section matches the agent's prioritization
    flags_res = client.get(
        f"/api/patients/{demo_patient_id}/flags",
        headers=headers,
    )
    assert flags_res.status_code == 200
    expected_top3 = flags_res.json()["top_concerns"]
    report_top3 = [card["concern"] for card in ctx["top3_cards"]]
    assert report_top3 == expected_top3

    # Exit criterion 5: Page 3 hypotheses render with disclaimer
    assert len(ctx["flag_rows"]) == 12
    for f_row in ctx["flag_rows"]:
        assert CLINICAL_DISCLAIMER in f_row["hypothesis"]
        assert f'data-flag-concern="{f_row["concern"]}"' in html_str


def test_report_graceful_placeholder_when_mask_urls_unavailable(
    migrated_db_session: Session,
) -> None:
    """Exit criterion 6: No broken images when mask_urls are unavailable (graceful placeholder)."""
    seed_info = seed_demo_longitudinal(migrated_db_session)
    demo_patient_id = uuid.UUID(seed_info["demo_patient_id"])

    # Wipe all mask_url and mask_storage_key values
    migrated_db_session.execute(
        update(ConcernScore).values(mask_url=None, mask_storage_key=None)
    )
    migrated_db_session.commit()

    pdf_bytes, html_str, ctx = build_patient_report_pdf(
        migrated_db_session,
        demo_patient_id,
    )
    assert pdf_bytes.startswith(b"%PDF-1.")
    assert len(re.findall(rb"/Type\s*/Page\b", pdf_bytes)) == 3

    for card in ctx["top3_cards"]:
        assert card["mask_status"] == "placeholder"
        assert card["mask_data_uri"].startswith("data:image/png;base64,")
        assert len(card["mask_data_uri"]) > 100

    assert 'src=""' not in html_str
    assert "Overlay Placeholder" in html_str


def test_fhir_export_validates_against_observation_schema(
    client: TestClient,
    migrated_db_session: Session,
) -> None:
    """Exit criterion 7: FHIR JSON validates against Observation schema shape."""
    seed_info = seed_demo_longitudinal(migrated_db_session)
    demo_patient_id = seed_info["demo_patient_id"]
    settings = Settings(_env_file=None)
    headers = _auth_headers(client, settings)

    res = client.get(f"/api/patients/{demo_patient_id}/fhir", headers=headers)
    assert res.status_code == 200
    bundle_data = res.json()

    # Validate against strict Pydantic FHIR R4 Bundle & Observation schemas
    bundle = FHIRBundle.model_validate(bundle_data)
    assert bundle.resourceType == "Bundle"
    assert bundle.total == 36  # 3 visits * 12 concerns
    assert len(bundle.entry) == 36

    seen_concerns: set[str] = set()
    for entry in bundle.entry:
        obs = FHIRObservation.model_validate(entry.resource.model_dump())
        assert obs.resourceType == "Observation"
        assert obs.status == "final"
        assert obs.subject.reference == f"Patient/{demo_patient_id}"
        assert 0.0 <= obs.valueQuantity.value <= 100.0
        assert obs.note[0].text == CLINICAL_DISCLAIMER
        seen_concerns.add(obs.code.coding[0].code)

    assert seen_concerns == set(CONCERN_LIST)
