"""Selects top 3 concerns by |delta| x complaint relevance; returns indices only, no prose.

For clinician review — not a diagnosis.
"""

from collections.abc import Sequence
from decimal import Decimal
from typing import Final

from app.domain.concerns import CONCERN_LABELS, CONCERN_LIST

COMPLAINT_RELEVANCE_BOOST: Final[float] = 1.5
BASE_RELEVANCE_WEIGHT: Final[float] = 1.0

CONCERN_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "acne": (
        "acne",
        "blemish",
        "breakout",
        "lesion",
        "comedone",
        "papule",
        "pustule",
        "adapalene",
        "retinoid",
        "salicylic",
    ),
    "wrinkle": (
        "wrinkle",
        "line",
        "fine line",
        "crease",
        "crow",
        "rhytid",
    ),
    "pores": (
        "pore",
        "enlarged pore",
        "congested",
    ),
    "texture": (
        "texture",
        "rough",
        "roughness",
        "uneven surface",
        "exfoliat",
        "glycolic",
    ),
    "redness": (
        "redness",
        "erythema",
        "flush",
        "irritat",
        "post-inflammatory",
        "rosacea",
    ),
    "oiliness": (
        "oil",
        "oily",
        "oiliness",
        "sebum",
        "shine",
    ),
    "moisture": (
        "moisture",
        "dry",
        "dryness",
        "dehydrat",
        "hydrat",
        "barrier",
        "ceramide",
    ),
    "radiance": (
        "radiance",
        "dull",
        "dullness",
        "glow",
        "bright",
    ),
    "firmness": (
        "firm",
        "firmness",
        "laxity",
        "sag",
        "elasticity",
    ),
    "dark_circle_v2": (
        "dark circle",
        "periorbital",
        "under-eye",
        "undereye",
    ),
    "dark_spot": (
        "dark spot",
        "spot",
        "hyperpigmentation",
        "pigmentation",
        "dyschromia",
        "melasma",
        "sun spot",
        "solar",
        "uv",
    ),
    "skin_tone": (
        "skin tone",
        "tone",
        "evenness",
        "discoloration",
    ),
}


def compute_complaint_relevance(concern: str, text_corpus: str) -> float:
    """Return relevance multiplier (1.5 if complaint/treatment text mentions concern, else 1.0)."""
    normalized = text_corpus.lower()
    if not normalized.strip():
        return BASE_RELEVANCE_WEIGHT

    keywords = CONCERN_KEYWORDS.get(concern, ())
    label = CONCERN_LABELS.get(concern, "").lower()
    if concern.lower() in normalized or (label and label in normalized):
        return COMPLAINT_RELEVANCE_BOOST

    for kw in keywords:
        if kw in normalized:
            return COMPLAINT_RELEVANCE_BOOST

    return BASE_RELEVANCE_WEIGHT


def prioritize_concerns(
    deltas_by_concern: dict[str, float | Decimal | None],
    complaint_texts: Sequence[str | None] | str | None = None,
    *,
    top_k: int = 3,
) -> list[int]:
    """Select top-K concern indices in CONCERN_LIST ordered by |delta| * complaint_relevance.

    Returns indices only (list[int] into CONCERN_LIST), never prose.
    """
    if isinstance(complaint_texts, str):
        corpus = complaint_texts
    elif complaint_texts is not None:
        corpus = " ".join(t for t in complaint_texts if t)
    else:
        corpus = ""

    scored_indices: list[tuple[float, int]] = []
    for idx, concern in enumerate(CONCERN_LIST):
        raw_delta = deltas_by_concern.get(concern)
        abs_delta = abs(float(raw_delta)) if raw_delta is not None else 0.0
        relevance = compute_complaint_relevance(concern, corpus)
        weighted_score = abs_delta * relevance
        scored_indices.append((weighted_score, idx))

    # Sort descending by weighted_score, breaking ties deterministically by index
    scored_indices.sort(key=lambda pair: (-pair[0], pair[1]))
    selected = [idx for _score, idx in scored_indices[: max(0, min(top_k, len(CONCERN_LIST)))]]
    return selected

