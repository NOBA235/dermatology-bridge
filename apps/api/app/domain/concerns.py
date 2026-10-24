"""Frozen skin concern list, direction-of-good map, and clinical labels.

For clinician review — not a diagnosis.
"""

from decimal import Decimal
from typing import Final, Literal

ConcernDirection = Literal["higher_is_better", "lower_is_better"]
SeverityBucket = Literal["clear", "mild", "moderate", "severe"]

# Frozen version tag stored on visits.analysis_version.
# Incrementing this requires a deliberate migration; visits with differing
# analysis_version values cannot be compared in longitudinal trend queries.
ANALYSIS_VERSION: Final[int] = 1

# Frozen 12-action concern list sent as dst_actions to YouCam S2S v2.0.
CONCERN_LIST: Final[tuple[str, ...]] = (
    "acne",
    "wrinkle",
    "pores",
    "texture",
    "redness",
    "oiliness",
    "moisture",
    "radiance",
    "firmness",
    "dark_circle_v2",
    "dark_spot",
    "skin_tone",
)

# Explicit direction-of-good map per concern.
# - lower_is_better: symptom/lesion burden score where 0 = absent and 100 = high burden
#   (e.g., a rising acne score indicates worsening; a falling acne score indicates improving).
# - higher_is_better: skin health/quality score where 100 = optimal and 0 = depleted
#   (e.g., a rising moisture score indicates improving; a falling moisture score indicates worsening).
CONCERN_DIRECTION: Final[dict[str, ConcernDirection]] = {
    "acne": "lower_is_better",
    "wrinkle": "lower_is_better",
    "pores": "lower_is_better",
    "texture": "lower_is_better",
    "redness": "lower_is_better",
    "oiliness": "lower_is_better",
    "moisture": "higher_is_better",
    "radiance": "higher_is_better",
    "firmness": "higher_is_better",
    "dark_circle_v2": "lower_is_better",
    "dark_spot": "lower_is_better",
    "skin_tone": "higher_is_better",
}

CONCERN_LABELS: Final[dict[str, str]] = {
    "acne": "Acne & Blemishes",
    "wrinkle": "Wrinkles & Fine Lines",
    "pores": "Visible Pores",
    "texture": "Skin Texture Roughness",
    "redness": "Erythema / Redness",
    "oiliness": "Sebum / Oiliness",
    "moisture": "Skin Moisture",
    "radiance": "Skin Radiance",
    "firmness": "Skin Firmness",
    "dark_circle_v2": "Periorbital Dark Circles",
    "dark_spot": "Hyperpigmentation / Spots",
    "skin_tone": "Skin Tone Evenness",
}


def score_to_severity(concern: str, score: float | Decimal) -> SeverityBucket:
    """Map a 0..100 concern score to a heuristic severity bucket ('clear','mild','moderate','severe').

    Note: These thresholds are non-diagnostic visual decision-support heuristics
    (For clinician review — not a diagnosis):
    - For lower_is_better concerns, burden = score.
    - For higher_is_better concerns, burden = 100 - score.
    - Burden thresholds: <25 -> 'clear', 25..<50 -> 'mild', 50..<75 -> 'moderate', >=75 -> 'severe'.
    """
    if concern not in CONCERN_DIRECTION:
        raise ValueError(f"Unknown concern {concern!r}; must be one of CONCERN_LIST.")

    numeric_score = float(score)
    if numeric_score < 0.0 or numeric_score > 100.0:
        raise ValueError(f"Score must be in [0, 100], got {numeric_score}")

    direction = CONCERN_DIRECTION[concern]
    burden = numeric_score if direction == "lower_is_better" else (100.0 - numeric_score)

    if burden < 25.0:
        return "clear"
    if burden < 50.0:
        return "mild"
    if burden < 75.0:
        return "moderate"
    return "severe"
