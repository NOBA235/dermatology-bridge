"""Longitudinal treatment-response flag thresholds (MDC) and verdict computation.

For clinician review — not a diagnosis.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Final, Literal

from app.domain.concerns import CONCERN_DIRECTION

Verdict = Literal["improving", "stalled", "worsening", "insufficient_data"]

MIN_DAYS_BETWEEN: Final[int] = 21
MIN_VISITS: Final[int] = 2

# Minimal Detectable Change (MDC) in points on the 0..100 scale per concern.
# Score movements smaller in magnitude than MDC (|delta| < MDC) are classified
# as 'stalled' to prevent over-interpreting capture/lighting noise between visits.
MDC_TABLE: Final[dict[str, float]] = {
    "acne": 5.0,
    "wrinkle": 4.0,
    "pores": 4.0,
    "texture": 4.0,
    "redness": 5.0,
    "oiliness": 5.0,
    "moisture": 5.0,
    "radiance": 4.0,
    "firmness": 4.0,
    "dark_circle_v2": 4.0,
    "dark_spot": 4.0,
    "skin_tone": 4.0,
}


def compute_delta_and_pct(
    baseline_score: float | Decimal | None,
    latest_score: float | Decimal | None,
) -> tuple[Decimal | None, Decimal | None]:
    """Compute signed delta (latest - baseline) and percentage change vs baseline."""
    if baseline_score is None or latest_score is None:
        return None, None

    base_dec = Decimal(str(baseline_score))
    latest_dec = Decimal(str(latest_score))
    delta = (latest_dec - base_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if base_dec == Decimal("0"):
        pct_change = None
    else:
        pct_change = ((delta / base_dec) * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    return delta, pct_change


def compute_verdict(
    concern: str,
    baseline_score: float | Decimal | None = None,
    latest_score: float | Decimal | None = None,
    days_between: int = MIN_DAYS_BETWEEN,
    visit_count: int = MIN_VISITS,
    *,
    delta: float | Decimal | None = None,
) -> Verdict:
    """Compute longitudinal treatment-response verdict for a single skin concern.

    Rules (For clinician review — not a diagnosis):
    1. If visit_count < MIN_VISITS (2) or days_between < MIN_DAYS_BETWEEN (21),
       return 'insufficient_data'.
    2. Compute delta = latest_score - baseline_score (unless delta is passed directly).
       If |delta| < MDC_TABLE[concern], return 'stalled'.
    3. Apply CONCERN_DIRECTION[concern]:
       - 'higher_is_better' (moisture, radiance, firmness, skin_tone):
         delta > 0 -> 'improving', delta < 0 -> 'worsening'
       - 'lower_is_better' (acne, wrinkle, pores, texture, redness, oiliness,
         dark_circle_v2, dark_spot):
         delta < 0 -> 'improving', delta > 0 -> 'worsening'
    """
    if concern not in CONCERN_DIRECTION or concern not in MDC_TABLE:
        raise ValueError(f"Unknown concern {concern!r}; must be in CONCERN_LIST.")

    if visit_count < MIN_VISITS or days_between < MIN_DAYS_BETWEEN:
        return "insufficient_data"

    if delta is None:
        if baseline_score is None or latest_score is None:
            return "insufficient_data"
        numeric_delta = float(latest_score) - float(baseline_score)
    else:
        numeric_delta = float(delta)

    mdc = MDC_TABLE[concern]
    if abs(numeric_delta) < mdc:
        return "stalled"

    direction = CONCERN_DIRECTION[concern]
    if direction == "higher_is_better":
        return "improving" if numeric_delta > 0 else "worsening"
    return "improving" if numeric_delta < 0 else "worsening"
