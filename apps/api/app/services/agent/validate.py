"""Grounding validator for agent narrative and attribution hypothesis outputs.

Critical path:
- Extracts every numeric token from agent prose output.
- Verifies each numeric token matches a value derived from source concern_scores
  within ±0.5 tolerance.
- Raises UngroundedClaim on any mismatch so the caller can regenerate once and
  then fall back to templates/narrative_fallback.md.
"""

from collections.abc import Sequence
from decimal import Decimal
import re
from typing import Any

from pydantic import BaseModel

from app import CLINICAL_DISCLAIMER

# Matches standalone signed/unsigned integers and decimals (e.g. 68, 68.00, -30.0, 44.1%)
# while ignoring digits attached to identifier prefixes like 'dark_circle_v2'.
_NUMERIC_TOKEN_RE = re.compile(r"(?<![a-zA-Z_])-?\d+(?:\.\d+)?")

DEFAULT_TOLERANCE = 0.5


class UngroundedClaim(ValueError):
    """Raised when agent output contains a numeric claim not grounded in source concern_scores."""

    def __init__(self, message: str, *, ungrounded_value: float | None = None) -> None:
        super().__init__(message)
        self.ungrounded_value = ungrounded_value


def extract_numeric_tokens(text: str) -> list[float]:
    """Extract all numeric tokens from a narrative or hypothesis string."""
    if not text:
        return []
    return [float(match.group(0)) for match in _NUMERIC_TOKEN_RE.finditer(text)]


def collect_source_numbers(source_json: dict[str, Any]) -> list[float]:
    """Collect all grounded numeric values tracing to concern_scores from source JSON."""
    grounded: set[float] = set()

    def _add_num(val: Any) -> None:
        if val is None or isinstance(val, bool):
            return
        if isinstance(val, (int, float, Decimal)):
            fval = float(val)
            grounded.add(fval)
            grounded.add(abs(fval))
            return
        if isinstance(val, str):
            try:
                fval = float(val)
                grounded.add(fval)
                grounded.add(abs(fval))
            except ValueError:
                return

    concerns_list = source_json.get("concerns") or source_json.get("concern_scores") or []
    if isinstance(concerns_list, list):
        for item in concerns_list:
            if not isinstance(item, dict):
                continue
            for key in (
                "score",
                "baseline_score",
                "latest_score",
                "delta",
                "pct_change",
            ):
                _add_num(item.get(key))

            points = item.get("points") or []
            if isinstance(points, list):
                for pt in points:
                    if isinstance(pt, dict):
                        _add_num(pt.get("score"))

    visits_list = source_json.get("visits") or []
    if isinstance(visits_list, list):
        for visit in visits_list:
            if not isinstance(visit, dict):
                continue
            for cs in visit.get("concern_scores") or []:
                if isinstance(cs, dict):
                    _add_num(cs.get("score"))

    return sorted(grounded)


def verify_numbers_against_source(
    text: str,
    source_numbers: Sequence[float],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
) -> list[float]:
    """Verify every numeric token in text exists in source_numbers within ±tolerance."""
    tokens = extract_numeric_tokens(text)
    if not tokens:
        return []

    if not source_numbers:
        raise UngroundedClaim(
            f"Agent emitted numeric token {tokens[0]} but source concern_scores has no numbers.",
            ungrounded_value=tokens[0],
        )

    for token in tokens:
        matched = any(
            abs(token - ref) <= tolerance or abs(abs(token) - abs(ref)) <= tolerance
            for ref in source_numbers
        )
        if not matched:
            raise UngroundedClaim(
                f"Ungrounded numeric claim {token} not found within ±{tolerance} of source concern_scores {list(source_numbers)}.",
                ungrounded_value=token,
            )

    return tokens


def ensure_clinical_disclaimer(text: str) -> str:
    """Ensure the mandatory clinical disclaimer is appended to a hypothesis or summary string."""
    cleaned = text.strip()
    if not cleaned:
        return CLINICAL_DISCLAIMER
    if CLINICAL_DISCLAIMER in cleaned:
        return cleaned
    if not cleaned.endswith((".", "!", "?")):
        cleaned = f"{cleaned}."
    return f"{cleaned} {CLINICAL_DISCLAIMER}"


def validate_agent_output(
    agent_output: dict[str, Any] | BaseModel,
    source_json: dict[str, Any],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
) -> None:
    """Validate all prose fields in agent_output against source_json within ±tolerance."""
    payload = (
        agent_output.model_dump()
        if isinstance(agent_output, BaseModel)
        else dict(agent_output)
    )
    source_numbers = collect_source_numbers(source_json)

    summary = payload.get("summary")
    if isinstance(summary, str) and summary.strip():
        verify_numbers_against_source(summary, source_numbers, tolerance=tolerance)

    hypotheses = payload.get("hypotheses") or {}
    if isinstance(hypotheses, dict):
        for concern, hyp_text in hypotheses.items():
            if isinstance(hyp_text, str) and hyp_text.strip():
                verify_numbers_against_source(
                    hyp_text, source_numbers, tolerance=tolerance
                )
                if CLINICAL_DISCLAIMER not in hyp_text:
                    raise UngroundedClaim(
                        f"Hypothesis for {concern!r} is missing mandatory clinical disclaimer."
                    )
    elif isinstance(hypotheses, list):
        for item in hypotheses:
            if isinstance(item, dict):
                hyp_text = item.get("hypothesis") or ""
                if isinstance(hyp_text, str) and hyp_text.strip():
                    verify_numbers_against_source(
                        hyp_text, source_numbers, tolerance=tolerance
                    )
                    if CLINICAL_DISCLAIMER not in hyp_text:
                        raise UngroundedClaim(
                            "Hypothesis item is missing mandatory clinical disclaimer."
                        )

