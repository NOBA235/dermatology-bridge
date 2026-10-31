"""Domain rules and cross-referencing algorithms for patient medications.

Correlates medication start/stop dates with longitudinal skin concern trajectories
to evaluate clinical response, detect potential adverse flares, and calculate benchmarks.

For clinician review — not a diagnosis.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final, Literal

from app.domain.concerns import CONCERN_DIRECTION, CONCERN_LABELS
from app.domain.flags import MDC_TABLE, compute_delta_and_pct

MedicationCategory = Literal[
    "topical_retinoid",
    "oral_retinoid",
    "barrier_repair",
    "topical_acid",
    "anti_androgen",
    "oral_antibiotic",
    "topical_antimicrobial",
    "corticosteroid",
    "other",
]

ResponseStatus = Literal[
    "clinically_responsive",
    "early_favorable_trend",
    "minimal_change",
    "potential_adverse_flare",
    "insufficient_followup",
]

MEDICATION_CATEGORIES: Final[dict[str, str]] = {
    "topical_retinoid": "Topical Retinoid",
    "oral_retinoid": "Oral Retinoid",
    "barrier_repair": "Barrier Repair / Ceramide",
    "topical_acid": "Exfoliating Acid (AHA/BHA/Azelaic)",
    "anti_androgen": "Anti-Androgen (Spironolactone)",
    "oral_antibiotic": "Oral Antibiotic (Doxycycline/Minocycline)",
    "topical_antimicrobial": "Topical Antimicrobial (Benzoyl Peroxide/Clindamycin)",
    "corticosteroid": "Topical Corticosteroid",
    "other": "Other Dermatological Therapy",
}

# Target concerns and standard pharmacological onset lag (in days) per category
CATEGORY_PROFILES: Final[dict[str, dict[str, Any]]] = {
    "topical_retinoid": {
        "primary_concerns": ["acne", "texture", "pores", "wrinkle"],
        "adverse_watch": ["redness", "moisture"],
        "min_lag_days": 28,
    },
    "oral_retinoid": {
        "primary_concerns": ["acne", "oiliness", "pores", "texture"],
        "adverse_watch": ["moisture", "redness"],
        "min_lag_days": 28,
    },
    "barrier_repair": {
        "primary_concerns": ["moisture", "redness", "texture"],
        "adverse_watch": ["oiliness"],
        "min_lag_days": 14,
    },
    "topical_acid": {
        "primary_concerns": ["dark_spot", "texture", "acne"],
        "adverse_watch": ["redness", "moisture"],
        "min_lag_days": 21,
    },
    "anti_androgen": {
        "primary_concerns": ["acne", "oiliness"],
        "adverse_watch": [],
        "min_lag_days": 42,
    },
    "oral_antibiotic": {
        "primary_concerns": ["acne", "redness"],
        "adverse_watch": [],
        "min_lag_days": 21,
    },
    "topical_antimicrobial": {
        "primary_concerns": ["acne", "redness"],
        "adverse_watch": ["redness", "moisture"],
        "min_lag_days": 14,
    },
    "corticosteroid": {
        "primary_concerns": ["redness"],
        "adverse_watch": ["firmness"],
        "min_lag_days": 7,
    },
    "other": {
        "primary_concerns": ["acne", "redness", "moisture"],
        "adverse_watch": [],
        "min_lag_days": 21,
    },
}


@dataclass(frozen=True)
class ConcernResponseSummary:
    """Metric trajectory for a single concern relative to a medication."""

    concern: str
    label: str
    baseline_score: Decimal
    latest_score: Decimal
    delta: Decimal
    pct_change: Decimal | None
    mdc: float
    direction: str
    is_improved: bool
    is_worsened: bool
    exceeds_mdc: bool


@dataclass(frozen=True)
class MedicationCorrelationResult:
    """Cross-referenced clinical correlation for a patient medication."""

    medication_id: str
    medication_name: str
    category: str
    category_label: str
    dose: str | None
    start_date: date
    end_date: date | None
    is_active: bool
    days_on_therapy: int
    baseline_visit_date: date | None
    latest_visit_date: date | None
    response_status: ResponseStatus
    headline: str
    clinical_note: str
    concern_responses: list[ConcernResponseSummary]


def cross_reference_medication(
    medication_id: str,
    medication_name: str,
    category: str,
    dose: str | None,
    start_date: date,
    end_date: date | None,
    visits: list[dict[str, Any]],
) -> MedicationCorrelationResult:
    """Cross-reference a medication episode with chronological visit scores.

    visits must be sorted ascending by visit_date and contain:
    - 'visit_date': date
    - 'scores': dict[str, Decimal] (scores for the 12 concerns)
    """
    category_key = category if category in CATEGORY_PROFILES else "other"
    profile = CATEGORY_PROFILES[category_key]
    primary_concerns: list[str] = profile["primary_concerns"]
    adverse_watch: list[str] = profile["adverse_watch"]
    min_lag_days: int = profile["min_lag_days"]
    cat_label = MEDICATION_CATEGORIES.get(category, "Dermatological Therapy")

    effective_end = end_date or date.today()
    days_on_therapy = max((effective_end - start_date).days, 0)
    is_active = end_date is None

    if not visits:
        return MedicationCorrelationResult(
            medication_id=medication_id,
            medication_name=medication_name,
            category=category,
            category_label=cat_label,
            dose=dose,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active,
            days_on_therapy=days_on_therapy,
            baseline_visit_date=None,
            latest_visit_date=None,
            response_status="insufficient_followup",
            headline="No visit encounters recorded yet",
            clinical_note="Requires at least one baseline and one follow-up visit encounter.",
            concern_responses=[],
        )

    # 1. Identify baseline visit (the visit on or immediately preceding start_date)
    # If all visits are after start_date, the earliest visit becomes baseline.
    pre_visits = [v for v in visits if v["visit_date"] <= start_date]
    if pre_visits:
        baseline_visit = pre_visits[-1]
    else:
        baseline_visit = visits[0]

    # 2. Identify post-initiation follow-up visits
    post_visits = [v for v in visits if v["visit_date"] > baseline_visit["visit_date"]]
    if not post_visits:
        return MedicationCorrelationResult(
            medication_id=medication_id,
            medication_name=medication_name,
            category=category,
            category_label=cat_label,
            dose=dose,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active,
            days_on_therapy=days_on_therapy,
            baseline_visit_date=baseline_visit["visit_date"],
            latest_visit_date=None,
            response_status="insufficient_followup",
            headline=f"Baseline recorded on {baseline_visit['visit_date'].isoformat()} — awaiting follow-up",
            clinical_note="Treatment baseline captured. Schedule a follow-up encounter after the recommended pharmacological window.",
            concern_responses=[],
        )

    latest_visit = post_visits[-1]
    elapsed_days = (latest_visit["visit_date"] - start_date).days

    # 3. Analyze concern movements
    evaluated_concerns = list(dict.fromkeys(primary_concerns + adverse_watch))
    responses: list[ConcernResponseSummary] = []
    improved_primary_count = 0
    worsened_adverse_count = 0

    base_scores = baseline_visit.get("scores", {})
    latest_scores = latest_visit.get("scores", {})

    for concern in evaluated_concerns:
        if concern not in base_scores or concern not in latest_scores:
            continue

        b_score = Decimal(str(base_scores[concern]))
        l_score = Decimal(str(latest_scores[concern]))
        delta, pct = compute_delta_and_pct(b_score, l_score)
        if delta is None:
            continue

        mdc = MDC_TABLE.get(concern, 5.0)
        direction = CONCERN_DIRECTION.get(concern, "lower_is_better")
        exceeds_mdc = abs(float(delta)) >= mdc

        if direction == "lower_is_better":
            is_improved = delta <= Decimal(f"-{mdc}")
            is_worsened = delta >= Decimal(f"{mdc}")
        else:
            is_improved = delta >= Decimal(f"{mdc}")
            is_worsened = delta <= Decimal(f"-{mdc}")

        if concern in primary_concerns and is_improved:
            improved_primary_count += 1
        if concern in adverse_watch and is_worsened:
            worsened_adverse_count += 1

        responses.append(
            ConcernResponseSummary(
                concern=concern,
                label=CONCERN_LABELS.get(concern, concern),
                baseline_score=b_score,
                latest_score=l_score,
                delta=delta,
                pct_change=pct,
                mdc=mdc,
                direction=direction,
                is_improved=is_improved,
                is_worsened=is_worsened,
                exceeds_mdc=exceeds_mdc,
            )
        )

    # 4. Formulate response status and clinical headline
    if worsened_adverse_count > 0:
        status: ResponseStatus = "potential_adverse_flare"
        headline = f"Potential adverse flare or barrier disruption detected ({worsened_adverse_count} watch indicator worsened)"
        clinical_note = (
            f"Following {medication_name} ({dose or 'standard dose'}), barrier or irritation indicators "
            f"showed worsening exceeding the MDC threshold. Review patient tolerability and application frequency."
        )
    elif improved_primary_count > 0 and elapsed_days >= min_lag_days:
        status = "clinically_responsive"
        headline = f"Clinically responsive ({improved_primary_count} target metric{'s' if improved_primary_count > 1 else ''} improved beyond MDC)"
        clinical_note = (
            f"Sustained improvement observed across {improved_primary_count} target concern(s) over "
            f"{elapsed_days} days. Regimen is currently efficacious."
        )
    elif improved_primary_count > 0 and elapsed_days < min_lag_days:
        status = "early_favorable_trend"
        headline = f"Early favorable trajectory ({elapsed_days}d elapsed / {min_lag_days}d onset window)"
        clinical_note = (
            f"Early positive trend detected before the full pharmacological onset window ({min_lag_days} days). "
            f"Re-evaluate at the next planned encounter."
        )
    elif elapsed_days < min_lag_days:
        status = "insufficient_followup"
        headline = f"Within standard pharmacological onset window ({elapsed_days}d of {min_lag_days}d)"
        clinical_note = f"Drug concentration and cellular turnover requires {min_lag_days} days for detectable response."
    else:
        status = "minimal_change"
        headline = "Minimal change within measurement variability (|delta| < MDC)"
        clinical_note = (
            f"Scores for targeted concerns remained within the minimal detectable change threshold after {elapsed_days} days. "
            f"Consider patient compliance check, dose titration, or alternative mechanism of action."
        )

    return MedicationCorrelationResult(
        medication_id=medication_id,
        medication_name=medication_name,
        category=category,
        category_label=cat_label,
        dose=dose,
        start_date=start_date,
        end_date=end_date,
        is_active=is_active,
        days_on_therapy=days_on_therapy,
        baseline_visit_date=baseline_visit["visit_date"],
        latest_visit_date=latest_visit["visit_date"],
        response_status=status,
        headline=headline,
        clinical_note=clinical_note,
        concern_responses=responses,
    )

