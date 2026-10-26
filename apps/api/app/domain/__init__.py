"""Domain constants and rules for Dermatology Bridge."""

from app.domain.concerns import (
    ANALYSIS_VERSION,
    CONCERN_DIRECTION,
    CONCERN_LABELS,
    CONCERN_LIST,
    ConcernDirection,
    SeverityBucket,
    score_to_severity,
)
from app.domain.flags import (
    MDC_TABLE,
    MIN_DAYS_BETWEEN,
    MIN_VISITS,
    Verdict,
    compute_delta_and_pct,
    compute_verdict,
)
from app.domain.severity import (
    SEVERITY_THRESHOLDS,
    compute_burden_score,
    map_score_to_severity,
)

__all__ = [
    "ANALYSIS_VERSION",
    "CONCERN_DIRECTION",
    "CONCERN_LABELS",
    "CONCERN_LIST",
    "ConcernDirection",
    "MDC_TABLE",
    "MIN_DAYS_BETWEEN",
    "MIN_VISITS",
    "SEVERITY_THRESHOLDS",
    "SeverityBucket",
    "Verdict",
    "compute_burden_score",
    "compute_delta_and_pct",
    "compute_verdict",
    "map_score_to_severity",
    "score_to_severity",
]
