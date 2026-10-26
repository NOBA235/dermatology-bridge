"""Heuristic score-to-severity bucket mapping for skin concerns.

For clinician review — not a diagnosis.

Heuristic thresholds (0..100 scale):
- These cutoffs are visual decision-support heuristics for longitudinal grouping,
  NOT validated diagnostic or clinical staging thresholds.
- For 'lower_is_better' concerns (e.g. acne, redness, wrinkle, pores, texture,
  oiliness, dark_circle_v2, dark_spot), higher numeric scores represent higher
  visible concern burden:
    * [0.0, 25.0)   -> 'clear'
    * [25.0, 50.0)  -> 'mild'
    * [50.0, 75.0)  -> 'moderate'
    * [75.0, 100.0] -> 'severe'
- For 'higher_is_better' concerns (moisture, radiance, firmness, skin_tone),
  higher numeric scores represent healthier presentation, so effective burden is
  inverted (burden = 100.0 - score) before applying the same four bands:
    * score > 75.0  (burden < 25.0)  -> 'clear'
    * score > 50.0  (burden < 50.0)  -> 'mild'
    * score > 25.0  (burden < 75.0)  -> 'moderate'
    * score <= 25.0 (burden >= 75.0) -> 'severe'
"""

from decimal import Decimal
from typing import Final

from app.domain.concerns import CONCERN_DIRECTION, SeverityBucket

SEVERITY_THRESHOLDS: Final[tuple[tuple[float, SeverityBucket], ...]] = (
    (25.0, "clear"),
    (50.0, "mild"),
    (75.0, "moderate"),
    (100.01, "severe"),
)


def compute_burden_score(concern: str, score: float | Decimal) -> float:
    """Normalize a raw 0..100 concern score into a 0..100 burden value (higher = worse)."""
    if concern not in CONCERN_DIRECTION:
        raise ValueError(f"Unknown concern {concern!r}; must be in CONCERN_DIRECTION.")

    numeric_score = float(score)
    if numeric_score < 0.0 or numeric_score > 100.0:
        raise ValueError(f"Score must be between 0 and 100 inclusive, got {numeric_score}.")

    direction = CONCERN_DIRECTION[concern]
    return numeric_score if direction == "lower_is_better" else (100.0 - numeric_score)


def map_score_to_severity(concern: str, score: float | Decimal) -> SeverityBucket:
    """Map a 0..100 concern score to its heuristic severity bucket ('clear','mild','moderate','severe')."""
    burden = compute_burden_score(concern, score)
    for upper_bound, bucket in SEVERITY_THRESHOLDS:
        if burden < upper_bound:
            return bucket
    return "severe"
