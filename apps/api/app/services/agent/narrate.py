"""Structured JSON agent narrative and attribution hypothesis generator (temperature=0).

Invariants:
- Never receives or inspects images; operates strictly on structured trend/visit JSON.
- Enforces Pydantic v2 schema validation (AgentNarrativeOutput) at temperature=0.
- Validates every numeric token against source concern_scores within ±0.5 via validate.py.
- On UngroundedClaim or schema failure: regenerates once, then falls back to
  templates/narrative_fallback.md.
- Every hypothesis string ends with 'For clinician review — not a diagnosis.'
"""

from collections.abc import Callable
import json
from pathlib import Path
import re
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import CLINICAL_DISCLAIMER
from app.config import REPO_ROOT
from app.domain.concerns import CONCERN_LABELS, CONCERN_LIST
from app.services.agent.prioritize import CONCERN_KEYWORDS, prioritize_concerns
from app.services.agent.validate import (
    DEFAULT_TOLERANCE,
    UngroundedClaim,
    ensure_clinical_disclaimer,
    validate_agent_output,
)

AGENT_TEMPERATURE: Final[float] = 0.0
FALLBACK_TEMPLATE_PATH: Final[Path] = REPO_ROOT / "templates" / "narrative_fallback.md"

AGENT_SYSTEM_PROMPT: Final[str] = (
    "You are a clinical dermatology decision-support assistant. "
    "Output ONLY valid JSON matching the AgentNarrativeOutput schema at temperature=0. "
    "Use ONLY numeric scores and deltas present in the provided concern_scores JSON. "
    "Do not emit any numbers that are not in concern_scores. "
    "Hedge all clinical statements and append 'For clinician review — not a diagnosis.' "
    "to every hypothesis string."
)


class AgentNarrativeOutput(BaseModel):
    """Pydantic v2 schema enforced on all agent narrative outputs."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(..., min_length=10)
    top_concern_indices: list[int] = Field(..., min_length=1, max_length=3)
    hypotheses: dict[str, str]
    used_fallback: bool = False
    disclaimer: str = CLINICAL_DISCLAIMER


def _strip_numbers_from_phrase(text: str) -> str:
    """Remove numeric digits/percentages from product phrases so only concern_scores numbers appear."""
    cleaned = re.sub(r"\b\d+(?:\.\d+)?%?(?:x/week|x/day)?\b", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-")
    return cleaned


def _find_temporal_treatment_link(
    concern: str,
    treatment_changes: list[str],
) -> str | None:
    """Identify a plausible temporal treatment link for a concern from treatment_changes."""
    if not treatment_changes:
        return None

    keywords = CONCERN_KEYWORDS.get(concern, ())
    # Prefer the most recent treatment_changes entry first
    for change_text in reversed(treatment_changes):
        if not change_text or not change_text.strip():
            continue
        lower_change = change_text.lower()
        if any(kw in lower_change for kw in keywords) or any(
            term in lower_change
            for term in (
                "adapalene",
                "retinoid",
                "ceramide",
                "niacinamide",
                "glycolic",
                "salicylic",
                "spf",
                "toner",
                "serum",
                "cream",
            )
        ):
            sanitized = _strip_numbers_from_phrase(change_text)
            if sanitized:
                return sanitized
    return None


def _draft_deterministic_json(source_json: dict[str, Any]) -> dict[str, Any]:
    """Produce grounded, schema-valid JSON at temperature=0 from structured source_json."""
    concerns_data = source_json.get("concerns") or []
    by_concern: dict[str, dict[str, Any]] = {
        item["concern"]: item
        for item in concerns_data
        if isinstance(item, dict) and "concern" in item
    }

    complaint_texts: list[str] = list(source_json.get("complaint_texts") or [])
    treatment_changes: list[str] = list(source_json.get("treatment_changes") or [])

    deltas_map = {
        c: by_concern.get(c, {}).get("delta")
        for c in CONCERN_LIST
    }
    top_indices = prioritize_concerns(
        deltas_map,
        complaint_texts + treatment_changes,
        top_k=3,
    )
    top_concerns = [CONCERN_LIST[i] for i in top_indices]

    # Build summary using only grounded scores/deltas from the top prioritized concerns
    summary_parts: list[str] = []
    for concern in top_concerns:
        item = by_concern.get(concern, {})
        label = CONCERN_LABELS.get(concern, concern)
        b_score = item.get("baseline_score")
        l_score = item.get("latest_score")
        delta = item.get("delta")
        verdict = item.get("verdict", "insufficient_data")
        if b_score is not None and l_score is not None and delta is not None:
            summary_parts.append(
                f"{label} ({verdict}: baseline {b_score} to latest {l_score}, delta {delta})"
            )
        elif b_score is not None:
            summary_parts.append(f"{label} (baseline {b_score}, insufficient longitudinal data)")

    if summary_parts:
        summary_body = (
            "Longitudinal priority review highlights "
            + "; ".join(summary_parts)
            + "."
        )
    else:
        summary_body = "Insufficient longitudinal visit data to compute multi-visit score trajectories."

    summary_str = ensure_clinical_disclaimer(summary_body)

    hypotheses: dict[str, str] = {}
    for concern in CONCERN_LIST:
        item = by_concern.get(concern, {})
        label = CONCERN_LABELS.get(concern, concern)
        b_score = item.get("baseline_score")
        l_score = item.get("latest_score")
        delta = item.get("delta")
        verdict = item.get("verdict", "insufficient_data")

        if b_score is None or l_score is None or delta is None or verdict == "insufficient_data":
            hyp = ensure_clinical_disclaimer(
                f"{label} has insufficient longitudinal interval data for trajectory attribution."
            )
            hypotheses[concern] = hyp
            continue

        treatment_link = _find_temporal_treatment_link(concern, treatment_changes)
        if treatment_link and verdict in ("improving", "worsening"):
            direction_phrase = (
                "favorable response potentially associated with"
                if verdict == "improving"
                else "worsening trajectory temporally associated with recent regimen change involving"
            )
            hyp_body = (
                f"{label} moved from baseline {b_score} to {l_score} (delta {delta}, {verdict}); "
                f"hypothesis suggests {direction_phrase} {treatment_link}."
            )
        elif verdict == "stalled":
            hyp_body = (
                f"{label} shifted from baseline {b_score} to {l_score} (delta {delta}), "
                f"remaining within minimal detectable change thresholds."
            )
        else:
            hyp_body = (
                f"{label} shifted from baseline {b_score} to {l_score} (delta {delta}, {verdict}) "
                f"across the longitudinal observation window."
            )

        hypotheses[concern] = ensure_clinical_disclaimer(hyp_body)

    return {
        "summary": summary_str,
        "top_concern_indices": top_indices,
        "hypotheses": hypotheses,
        "used_fallback": False,
        "disclaimer": CLINICAL_DISCLAIMER,
    }


def render_fallback_narrative(
    source_json: dict[str, Any],
    *,
    template_path: Path | None = None,
) -> AgentNarrativeOutput:
    """Render deterministic fallback narrative from templates/narrative_fallback.md."""
    resolved_path = template_path or FALLBACK_TEMPLATE_PATH
    template_text = resolved_path.read_text(encoding="utf-8").strip()

    concerns_data = source_json.get("concerns") or []
    by_concern: dict[str, dict[str, Any]] = {
        item["concern"]: item
        for item in concerns_data
        if isinstance(item, dict) and "concern" in item
    }
    complaint_texts: list[str] = list(source_json.get("complaint_texts") or [])
    treatment_changes: list[str] = list(source_json.get("treatment_changes") or [])

    deltas_map = {c: by_concern.get(c, {}).get("delta") for c in CONCERN_LIST}
    top_indices = prioritize_concerns(
        deltas_map,
        complaint_texts + treatment_changes,
        top_k=3,
    )
    lead_concern = CONCERN_LIST[top_indices[0]] if top_indices else CONCERN_LIST[0]
    lead_item = by_concern.get(lead_concern, {})

    lead_base = lead_item.get("baseline_score")
    lead_latest = lead_item.get("latest_score")
    lead_delta = lead_item.get("delta")

    if lead_base is not None and lead_latest is not None and lead_delta is not None:
        summary_str = ensure_clinical_disclaimer(
            template_text.format(
                baseline_score=lead_base,
                latest_score=lead_latest,
                delta=lead_delta,
                hypothesis_body=f"Primary tracked concern is {CONCERN_LABELS.get(lead_concern, lead_concern)}.",
            )
        )
    else:
        summary_str = ensure_clinical_disclaimer(
            "Longitudinal skin concern comparison has insufficient visit data."
        )

    hypotheses: dict[str, str] = {}
    for concern in CONCERN_LIST:
        item = by_concern.get(concern, {})
        label = CONCERN_LABELS.get(concern, concern)
        b_score = item.get("baseline_score")
        l_score = item.get("latest_score")
        delta = item.get("delta")
        verdict = item.get("verdict", "insufficient_data")

        if b_score is not None and l_score is not None and delta is not None:
            treatment_link = _find_temporal_treatment_link(concern, treatment_changes)
            if treatment_link:
                body = f"{label} ({verdict}) temporal review notes regimen adjustment ({treatment_link})."
            else:
                body = f"{label} ({verdict}) recorded across clinic visits."
            rendered = template_text.format(
                baseline_score=b_score,
                latest_score=l_score,
                delta=delta,
                hypothesis_body=body,
            )
            hypotheses[concern] = ensure_clinical_disclaimer(rendered)
        else:
            hypotheses[concern] = ensure_clinical_disclaimer(
                f"{label} has insufficient visit data for longitudinal comparison."
            )

    fallback_output = AgentNarrativeOutput(
        summary=summary_str,
        top_concern_indices=top_indices,
        hypotheses=hypotheses,
        used_fallback=True,
        disclaimer=CLINICAL_DISCLAIMER,
    )
    validate_agent_output(fallback_output, source_json, tolerance=DEFAULT_TOLERANCE)
    return fallback_output


def generate_narrative(
    source_json: dict[str, Any],
    *,
    llm_callable: Callable[[dict[str, Any], int], dict[str, Any] | str] | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> AgentNarrativeOutput:
    """Generate and validate structured narrative + hypotheses.

    Tries up to 2 attempts (initial + 1 retry on UngroundedClaim / ValidationError),
    then falls back deterministically to templates/narrative_fallback.md.
    """
    for attempt in range(2):
        try:
            if llm_callable is not None:
                raw_response = llm_callable(source_json, attempt)
                if isinstance(raw_response, str):
                    candidate_dict = json.loads(raw_response)
                else:
                    candidate_dict = dict(raw_response)
            else:
                candidate_dict = _draft_deterministic_json(source_json)

            # Ensure disclaimer on every hypothesis string before validation
            hyps = candidate_dict.get("hypotheses")
            if isinstance(hyps, dict):
                candidate_dict["hypotheses"] = {
                    k: ensure_clinical_disclaimer(str(v)) for k, v in hyps.items()
                }
            if "summary" in candidate_dict and isinstance(candidate_dict["summary"], str):
                candidate_dict["summary"] = ensure_clinical_disclaimer(
                    candidate_dict["summary"]
                )

            parsed = AgentNarrativeOutput.model_validate(candidate_dict)
            validate_agent_output(parsed, source_json, tolerance=tolerance)
            return parsed
        except (UngroundedClaim, ValidationError, json.JSONDecodeError, KeyError, TypeError):
            continue

    return render_fallback_narrative(source_json)
