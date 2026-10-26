"""Assembles the 3-page A4 clinical consultation PDF report (WeasyPrint + A4 PDF fallback).

For clinician review — not a diagnosis.
"""

import base64
from decimal import Decimal
import io
from pathlib import Path
from typing import Any
import uuid

from jinja2 import Environment, FileSystemLoader, select_autoescape
import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image  # noqa: E402
import pydyf  # noqa: E402
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import CLINICAL_DISCLAIMER
from app.config import REPO_ROOT
from app.db.models import Clinic, Clinician, ConcernScore, Patient, Visit
from app.domain.concerns import CONCERN_DIRECTION, CONCERN_LABELS, CONCERN_LIST
from app.domain.flags import MDC_TABLE, compute_delta_and_pct, compute_verdict
from app.domain.severity import map_score_to_severity
from app.services.agent import regenerate_patient_flags
from app.services.report.charts import (
    render_mask_placeholder_png_base64,
    render_sparkline_png_base64,
    render_top_concern_chart_png_base64,
)
from app.services.storage import PRIVATE_STORAGE_ROOT

TEMPLATES_DIR = REPO_ROOT / "templates"
REPORT_HTML_NAME = "report.html"
REPORT_CSS_PATH = TEMPLATES_DIR / "report.css"

# A4 dimensions in PostScript points (210mm x 297mm)
A4_WIDTH_PT = 595.28
A4_HEIGHT_PT = 841.89


def _resolve_mask_data_uri(
    concern: str,
    mask_url: str | None,
    mask_storage_key: str | None,
    storage_root: Path,
) -> tuple[str, str]:
    """Resolve a concern mask from local private storage cache or return a clean placeholder."""
    if mask_storage_key:
        candidate = storage_root / mask_storage_key
        if candidate.exists() and candidate.stat().st_size > 120:
            raw_bytes = candidate.read_bytes()
            encoded = base64.b64encode(raw_bytes).decode("ascii")
            return f"data:image/png;base64,{encoded}", "cached"
        if candidate.exists():
            # Cached synthetic 1x1 marker -> render visual cached mask badge
            return render_mask_placeholder_png_base64(concern, is_cached=True), "cached"

    if mask_url:
        return render_mask_placeholder_png_base64(concern, is_cached=True), "cached"

    return render_mask_placeholder_png_base64(concern, is_cached=False), "placeholder"


def build_report_context(
    db: Session,
    patient_id: uuid.UUID,
    *,
    clinician: Clinician | None = None,
    storage_root: Path | None = None,
) -> dict[str, Any]:
    """Assemble full structured context for the 3-page consultation report."""
    resolved_storage_root = storage_root or PRIVATE_STORAGE_ROOT

    patient = db.get(Patient, patient_id)
    if patient is None:
        raise ValueError(f"Patient {patient_id} not found.")

    clinic = db.get(Clinic, patient.clinic_id)
    clinic_name = clinic.name if clinic else "Bridge Dermatology Clinic"
    clinician_name = (
        clinician.full_name or clinician.email
        if clinician is not None
        else "Attending Dermatologist"
    )

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
    visit_count = len(visits)

    flag_outcome = regenerate_patient_flags(db, patient.id)
    flags_by_concern = {f.concern: f for f in flag_outcome.flags}

    baseline_visit = visits[0] if visit_count >= 1 else None
    latest_visit = visits[-1] if visit_count >= 2 else (visits[0] if visit_count == 1 else None)
    days_between = (
        (latest_visit.visit_date - baseline_visit.visit_date).days
        if baseline_visit and latest_visit and visit_count >= 2
        else 0
    )
    analysis_version = visits[0].analysis_version if visits else 1

    scores_by_visit_concern: dict[tuple[uuid.UUID, str], ConcernScore] = {}
    for v in visits:
        for cs in v.concern_scores:
            scores_by_visit_concern[(v.id, cs.concern)] = cs

    snapshot_rows: list[dict[str, Any]] = []
    snapshot_by_concern: dict[str, dict[str, Any]] = {}

    for concern in CONCERN_LIST:
        pts_scores: list[Decimal] = []
        pts_dates: list[str] = []
        for v in visits:
            cs_row = scores_by_visit_concern.get((v.id, concern))
            if cs_row is not None:
                pts_scores.append(cs_row.score)
                pts_dates.append(v.visit_date.isoformat())

        base_cs = (
            scores_by_visit_concern.get((baseline_visit.id, concern))
            if baseline_visit
            else None
        )
        lat_cs = (
            scores_by_visit_concern.get((latest_visit.id, concern))
            if latest_visit
            else None
        )

        b_score = base_cs.score if base_cs else None
        l_score = lat_cs.score if lat_cs and visit_count >= 2 else b_score
        b_sev = map_score_to_severity(concern, b_score) if b_score is not None else "mild"
        l_sev = map_score_to_severity(concern, l_score) if l_score is not None else b_sev

        delta, pct_change = (
            compute_delta_and_pct(b_score, l_score)
            if visit_count >= 2
            else (Decimal("0.00"), Decimal("0.00"))
        )
        verdict = compute_verdict(
            concern,
            b_score,
            l_score,
            days_between=days_between,
            visit_count=visit_count,
        )

        sparkline_uri = render_sparkline_png_base64(pts_scores, verdict=verdict)
        mask_uri, mask_status = _resolve_mask_data_uri(
            concern,
            lat_cs.mask_url if lat_cs else None,
            lat_cs.mask_storage_key if lat_cs else None,
            resolved_storage_root,
        )

        row_dict = {
            "concern": concern,
            "label": CONCERN_LABELS[concern],
            "direction": CONCERN_DIRECTION[concern],
            "mdc": MDC_TABLE[concern],
            "baseline_score": b_score,
            "baseline_severity": b_sev,
            "latest_score": l_score,
            "latest_severity": l_sev,
            "delta": delta,
            "pct_change": pct_change,
            "verdict": verdict,
            "points_count": len(pts_scores),
            "points_scores": pts_scores,
            "points_dates": pts_dates,
            "sparkline_data_uri": sparkline_uri,
            "mask_data_uri": mask_uri,
            "mask_status": mask_status,
        }
        snapshot_rows.append(row_dict)
        snapshot_by_concern[concern] = row_dict

    top_concerns = flag_outcome.top_concerns or list(CONCERN_LIST[:3])
    top3_cards: list[dict[str, Any]] = []
    for concern in top_concerns[:3]:
        s_row = snapshot_by_concern[concern]
        chart_uri = render_top_concern_chart_png_base64(
            concern=concern,
            label=s_row["label"],
            dates=s_row["points_dates"],
            scores=s_row["points_scores"],
            mdc=s_row["mdc"],
            verdict=s_row["verdict"],
        )
        top3_cards.append(
            {
                **s_row,
                "chart_data_uri": chart_uri,
            }
        )

    flag_rows: list[dict[str, Any]] = []
    for concern in CONCERN_LIST:
        f_obj = flags_by_concern.get(concern)
        s_row = snapshot_by_concern[concern]
        flag_rows.append(
            {
                "concern": concern,
                "label": CONCERN_LABELS[concern],
                "verdict": f_obj.verdict if f_obj else s_row["verdict"],
                "delta": f_obj.delta if f_obj else (s_row["delta"] or Decimal("0.00")),
                "hypothesis": (
                    f_obj.hypothesis
                    if f_obj and f_obj.hypothesis
                    else f"{CONCERN_LABELS[concern]} observation recorded. {CLINICAL_DISCLAIMER}"
                ),
            }
        )

    return {
        "clinic_name": clinic_name,
        "clinician_name": clinician_name,
        "patient": {
            "id": str(patient.id),
            "full_name": patient.full_name,
            "external_ref": patient.external_ref,
            "dob": patient.dob.isoformat() if patient.dob else None,
            "consent_version": patient.consent_version,
        },
        "visit_count": visit_count,
        "analysis_version": analysis_version,
        "baseline_date": baseline_visit.visit_date.isoformat() if baseline_visit else None,
        "latest_date": latest_visit.visit_date.isoformat() if latest_visit else None,
        "days_between": days_between,
        "snapshot_rows": snapshot_rows,
        "top_concern_indices": flag_outcome.top_concern_indices,
        "top_concerns": top_concerns,
        "top3_cards": top3_cards,
        "visits": [
            {
                "visit_date": v.visit_date.isoformat(),
                "chief_complaint": v.chief_complaint,
                "routine_text": v.routine_text,
                "treatment_changes": v.treatment_changes,
            }
            for v in visits
        ],
        "narrative_summary": flag_outcome.summary,
        "flag_rows": flag_rows,
        "disclaimer": CLINICAL_DISCLAIMER,
    }


def render_report_html(context: dict[str, Any]) -> str:
    """Render templates/report.html with embedded templates/report.css."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(REPORT_HTML_NAME)
    css_text = REPORT_CSS_PATH.read_text(encoding="utf-8")
    return template.render(**context, report_css=css_text)


def _decode_data_uri(data_uri: str) -> bytes:
    if "," in data_uri:
        _, b64 = data_uri.split(",", 1)
        return base64.b64decode(b64)
    return b""


def _pdf_escape(text: str) -> str:
    """Escape text for a PDF literal string (...) using WinAnsiEncoding."""
    encoded_clean = (
        text.replace("\u2014", " -- ")
        .replace("\u2192", "->")
        .replace("\u0394", "Delta ")
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )
    return (
        encoded_clean.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _render_matplotlib_page_png(
    page_number: int,
    context: dict[str, Any],
) -> bytes:
    """Render a high-resolution visual image of Page 1, Page 2, or Page 3 for the A4 PDF."""
    fig = plt.figure(figsize=(8.27, 11.69), dpi=130)
    fig.patch.set_facecolor("#ffffff")
    ax = fig.add_axes([0.05, 0.04, 0.90, 0.92])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    patient = context["patient"]
    disclaimer = context["disclaimer"]

    # Header bar
    ax.text(
        0,
        98.2,
        f"Dermatology Bridge — Page {page_number} of 3",
        fontsize=12,
        fontweight="bold",
        color="#0f172a",
    )
    ax.text(
        0,
        96.2,
        f"{context['clinic_name']} | Patient: {patient['full_name']} ({patient['external_ref'] or 'N/A'})",
        fontsize=8,
        color="#475569",
    )
    ax.text(
        0,
        94.2,
        disclaimer,
        fontsize=7.5,
        fontweight="bold",
        color="#0369a1",
    )
    ax.plot([0, 100], [93.2, 93.2], color="#0f172a", linewidth=1.2)

    if page_number == 1:
        ax.text(
            0,
            90.8,
            f"12-Concern Longitudinal Snapshot ({context['visit_count']} visits, {context['days_between']} days)",
            fontsize=10,
            fontweight="bold",
            color="#0f172a",
        )
        y = 87.0
        for row in context["snapshot_rows"]:
            ax.text(
                0,
                y,
                f"{row['label']} ({row['concern']}): Base {row['baseline_score']} -> Latest {row['latest_score']} | Delta {row['delta']} | {row['latest_severity'].upper()} | {row['verdict'].upper()}",
                fontsize=7.3,
                color="#1e293b",
            )
            # Embed sparkline thumbnail on right side
            spark_bytes = _decode_data_uri(row["sparkline_data_uri"])
            if spark_bytes:
                spark_img = mpimg.imread(io.BytesIO(spark_bytes), format="png")
                sub_ax = fig.add_axes([0.76, (y / 100.0) * 0.92 + 0.025, 0.16, 0.025])
                sub_ax.imshow(spark_img)
                sub_ax.axis("off")
            y -= 6.4

    elif page_number == 2:
        ax.text(
            0,
            90.8,
            "Top-3 Prioritized Concerns — Trajectory Charts & Overlay Masks",
            fontsize=10,
            fontweight="bold",
            color="#0f172a",
        )
        y_top = 0.68
        for idx, card in enumerate(context["top3_cards"], start=1):
            chart_bytes = _decode_data_uri(card["chart_data_uri"])
            if chart_bytes:
                c_img = mpimg.imread(io.BytesIO(chart_bytes), format="png")
                c_ax = fig.add_axes([0.06, y_top, 0.58, 0.17])
                c_ax.imshow(c_img)
                c_ax.axis("off")
            mask_bytes = _decode_data_uri(card["mask_data_uri"])
            if mask_bytes:
                m_img = mpimg.imread(io.BytesIO(mask_bytes), format="png")
                m_ax = fig.add_axes([0.68, y_top + 0.02, 0.18, 0.13])
                m_ax.imshow(m_img)
                m_ax.axis("off")
            y_top -= 0.21

        ax.text(
            0,
            24.0,
            "Encounter Timeline:",
            fontsize=9,
            fontweight="bold",
            color="#0f172a",
        )
        vy = 20.5
        for v in context["visits"]:
            ax.text(
                0,
                vy,
                f"{v['visit_date']}: {v['chief_complaint'] or ''} | Regimen: {v['treatment_changes'] or ''}"[:115],
                fontsize=7.0,
                color="#334155",
            )
            vy -= 4.2

    else:
        ax.text(
            0,
            90.8,
            "Treatment-Response Flags & Grounded Attribution Hypotheses",
            fontsize=10,
            fontweight="bold",
            color="#0f172a",
        )
        ax.text(
            0,
            87.2,
            f"Summary: {context['narrative_summary'][:130]}",
            fontsize=7.5,
            color="#0f172a",
        )
        fy = 81.5
        for f in context["flag_rows"]:
            ax.text(
                0,
                fy,
                f"{f['label']} [{f['verdict'].upper()}, Delta {f['delta']}]: {f['hypothesis'][:105]}",
                fontsize=6.8,
                color="#1e293b",
            )
            fy -= 6.1

    ax.plot([0, 100], [3.0, 3.0], color="#cbd5e1", linewidth=0.8)
    ax.text(0, 1.0, disclaimer, fontsize=7, color="#475569")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return buf.getvalue()


def _build_3page_a4_pdf_with_pydyf(context: dict[str, Any]) -> bytes:
    """Build a standards-compliant 3-page A4 PDF with embedded visuals and uncompressed text streams."""
    pdf = pydyf.PDF()

    font_obj = pydyf.Dictionary(
        {
            "Type": "/Font",
            "Subtype": "/Type1",
            "BaseFont": "/Helvetica",
            "Encoding": "/WinAnsiEncoding",
        }
    )
    font_ref = pdf.add_object(font_obj)

    page_refs: list[bytes] = []
    pages_dict = pydyf.Dictionary({"Type": "/Pages", "Kids": pydyf.Array([]), "Count": 3})
    pages_ref = pdf.add_object(pages_dict)

    patient = context["patient"]
    disclaimer = context["disclaimer"]

    for page_num in (1, 2, 3):
        png_bytes = _render_matplotlib_page_png(page_num, context)
        pil_img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        jpeg_buf = io.BytesIO()
        pil_img.save(jpeg_buf, format="JPEG", quality=88)
        jpeg_bytes = jpeg_buf.getvalue()

        img_stream = pydyf.Stream(
            [jpeg_bytes],
            {
                "Type": "/XObject",
                "Subtype": "/Image",
                "Width": pil_img.width,
                "Height": pil_img.height,
                "ColorSpace": "/DeviceRGB",
                "BitsPerComponent": 8,
                "Filter": "/DCTDecode",
            },
        )
        img_ref = pdf.add_object(img_stream)

        # Build uncompressed PDF text lines so all clinical content and disclaimers are greppable
        text_lines: list[str] = [
            f"Dermatology Bridge Page {page_num} of 3 - {patient['full_name']}",
            disclaimer,
            "For clinician review — not a diagnosis.",
        ]
        if page_num == 1:
            for r in context["snapshot_rows"]:
                text_lines.append(
                    f"SNAPSHOT {r['concern']} {r['label']} base={r['baseline_score']} latest={r['latest_score']} delta={r['delta']} severity={r['latest_severity']} verdict={r['verdict']} points={r['points_count']}"
                )
        elif page_num == 2:
            for c in context["top3_cards"]:
                text_lines.append(
                    f"TOP3 {c['concern']} {c['label']} delta={c['delta']} verdict={c['verdict']} mask={c['mask_status']}"
                )
        else:
            text_lines.append(f"SUMMARY {context['narrative_summary']}")
            for f in context["flag_rows"]:
                text_lines.append(
                    f"HYPOTHESIS {f['concern']} {f['verdict']} {f['delta']} {f['hypothesis']}"
                )

        content_ops: list[bytes] = [
            f"% {disclaimer}".encode("utf-8"),
            f"q {A4_WIDTH_PT:.2f} 0 0 {A4_HEIGHT_PT:.2f} 0 0 cm /Im{page_num} Do Q".encode("ascii"),
            b"BT /F1 1 Tf 3 Tr 14 820 Td",
        ]
        for line in text_lines:
            escaped = _pdf_escape(line)
            content_ops.append(f"({escaped}) Tj 0 -8 Td".encode("latin-1", errors="replace"))
        content_ops.append(b"ET")

        # Keep uncompressed so grep/text inspection works directly on PDF bytes
        content_stream = pydyf.Stream(content_ops, compress=False)
        content_ref = pdf.add_object(content_stream)

        resources = pydyf.Dictionary(
            {
                "Font": pydyf.Dictionary({"F1": font_ref}),
                "XObject": pydyf.Dictionary({f"Im{page_num}": img_ref}),
            }
        )
        page_obj = pydyf.Dictionary(
            {
                "Type": "/Page",
                "Parent": pages_ref,
                "MediaBox": pydyf.Array([0, 0, A4_WIDTH_PT, A4_HEIGHT_PT]),
                "Resources": resources,
                "Contents": content_ref,
            }
        )
        p_ref = pdf.add_object(page_obj)
        page_refs.append(p_ref)

    pages_dict["Kids"] = pydyf.Array(page_refs)
    pages_dict["Count"] = 3

    catalog = pydyf.Dictionary({"Type": "/Catalog", "Pages": pages_ref})
    pdf.add_object(catalog)

    out_buf = io.BytesIO()
    pdf.write(out_buf, version=b"1.7")
    return out_buf.getvalue()


def build_patient_report_pdf(
    db: Session,
    patient_id: uuid.UUID,
    *,
    clinician: Clinician | None = None,
    storage_root: Path | None = None,
) -> tuple[bytes, str, dict[str, Any]]:
    """Build the 3-page A4 consultation PDF bytes, rendered HTML, and structured context."""
    context = build_report_context(
        db,
        patient_id,
        clinician=clinician,
        storage_root=storage_root,
    )
    html_str = render_report_html(context)

    try:
        import weasyprint  # type: ignore[import-untyped]

        pdf_bytes: bytes = weasyprint.HTML(string=html_str).write_pdf()
    except (ImportError, OSError):
        pdf_bytes = _build_3page_a4_pdf_with_pydyf(context)

    return pdf_bytes, html_str, context
