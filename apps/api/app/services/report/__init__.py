"""Report generation, chart rendering, and FHIR Observation export package."""

from app.services.report.build import (
    A4_HEIGHT_PT,
    A4_WIDTH_PT,
    build_patient_report_pdf,
    build_report_context,
    render_report_html,
)
from app.services.report.charts import (
    render_mask_placeholder_png_base64,
    render_mask_placeholder_png_bytes,
    render_sparkline_png_base64,
    render_sparkline_png_bytes,
    render_top_concern_chart_png_base64,
    render_top_concern_chart_png_bytes,
)
from app.services.report.fhir import (
    FHIRAnnotation,
    FHIRBundle,
    FHIRBundleEntry,
    FHIRCodeableConcept,
    FHIRCoding,
    FHIRObservation,
    FHIRQuantity,
    FHIRReference,
    build_patient_fhir_bundle,
)

__all__ = [
    "A4_HEIGHT_PT",
    "A4_WIDTH_PT",
    "FHIRAnnotation",
    "FHIRBundle",
    "FHIRBundleEntry",
    "FHIRCodeableConcept",
    "FHIRCoding",
    "FHIRObservation",
    "FHIRQuantity",
    "FHIRReference",
    "build_patient_fhir_bundle",
    "build_patient_report_pdf",
    "build_report_context",
    "render_mask_placeholder_png_base64",
    "render_mask_placeholder_png_bytes",
    "render_report_html",
    "render_sparkline_png_base64",
    "render_sparkline_png_bytes",
    "render_top_concern_chart_png_base64",
    "render_top_concern_chart_png_bytes",
]

