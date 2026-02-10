"""
KuSubstanceService — Extracted Substance Scoring
=================================================

"Applied knowledge, not pure theory."

Pure scoring functions extracted from the Ku model to separate
computation from data. All methods are static — no state, no caching.

Weighting (from Knowledge Substance Philosophy):
    Habits   0.10/habit  (max 0.30) — lifestyle integration
    Journals 0.07/entry  (max 0.20) — metacognition
    Events   0.05/event  (max 0.25) — dedicated practice
    Tasks    0.05/task   (max 0.25) — practical application
    Choices  0.07/choice (max 0.15) — decision wisdom

Time decay: exponential with 30-day half-life, floor at 0.2.

See: /docs/architecture/knowledge_substance_philosophy.md
"""

from __future__ import annotations

from datetime import datetime
from math import exp, log
from typing import Any, Protocol


class SubstanceCarrier(Protocol):
    """Protocol for any object carrying substance counter fields.

    Both Ku (frozen dataclass) and KuDTO (mutable) satisfy this protocol.
    """

    times_applied_in_tasks: int
    times_practiced_in_events: int
    times_built_into_habits: int
    journal_reflections_count: int
    choices_informed_count: int
    last_applied_date: datetime | None
    last_practiced_date: datetime | None
    last_built_into_habit_date: datetime | None
    last_reflected_date: datetime | None
    last_choice_informed_date: datetime | None
    title: str


# =========================================================================
# CONSTANTS
# =========================================================================

HALF_LIFE_DAYS = 30.0
DECAY_FLOOR = 0.2

# Per-type weights and caps
HABIT_WEIGHT = 0.10
HABIT_CAP = 0.30
JOURNAL_WEIGHT = 0.07
JOURNAL_CAP = 0.20
EVENT_WEIGHT = 0.05
EVENT_CAP = 0.25
TASK_WEIGHT = 0.05
TASK_CAP = 0.25
CHOICE_WEIGHT = 0.07
CHOICE_CAP = 0.15


# =========================================================================
# PURE SCORING FUNCTIONS
# =========================================================================


def decay_weight(
    last_use_date: datetime | None,
    now: datetime,
    half_life_days: float = HALF_LIFE_DAYS,
) -> float:
    """Exponential decay: e^(-days / half_life), floor at 0.2."""
    if not last_use_date:
        return DECAY_FLOOR
    days_since_use = (now - last_use_date).days
    return max(DECAY_FLOOR, exp(-days_since_use / half_life_days))


def calculate_substance_score(carrier: SubstanceCarrier) -> float:
    """Calculate substance score with time decay (spaced repetition).

    Args:
        carrier: Any object with substance counter fields (Ku or KuDTO).

    Returns:
        Score in range [0.0, 1.0].
    """
    now = datetime.now()
    score = 0.0

    if carrier.times_built_into_habits > 0:
        w = decay_weight(carrier.last_built_into_habit_date, now)
        score += min(HABIT_CAP, carrier.times_built_into_habits * HABIT_WEIGHT * w)

    if carrier.journal_reflections_count > 0:
        w = decay_weight(carrier.last_reflected_date, now)
        score += min(JOURNAL_CAP, carrier.journal_reflections_count * JOURNAL_WEIGHT * w)

    if carrier.times_practiced_in_events > 0:
        w = decay_weight(carrier.last_practiced_date, now)
        score += min(EVENT_CAP, carrier.times_practiced_in_events * EVENT_WEIGHT * w)

    if carrier.times_applied_in_tasks > 0:
        w = decay_weight(carrier.last_applied_date, now)
        score += min(TASK_CAP, carrier.times_applied_in_tasks * TASK_WEIGHT * w)

    if carrier.choices_informed_count > 0:
        w = decay_weight(carrier.last_choice_informed_date, now)
        score += min(CHOICE_CAP, carrier.choices_informed_count * CHOICE_WEIGHT * w)

    return min(1.0, score)


def is_theoretical_only(carrier: SubstanceCarrier) -> bool:
    """Substance < 0.2 = pure theory."""
    return calculate_substance_score(carrier) < 0.2


def is_well_practiced(carrier: SubstanceCarrier) -> bool:
    """Substance >= 0.7 = deeply embedded."""
    return calculate_substance_score(carrier) >= 0.7


def needs_more_practice(carrier: SubstanceCarrier) -> bool:
    """Check if knowledge needs more real-world application."""
    return (
        carrier.times_applied_in_tasks < 3
        or carrier.times_practiced_in_events < 2
        or carrier.times_built_into_habits == 0
    )


def get_substantiation_gaps(carrier: SubstanceCarrier) -> list[str]:
    """Identify missing substantiation types for UI recommendations."""
    gaps = []
    if carrier.times_applied_in_tasks == 0:
        gaps.append("No tasks apply this knowledge")
    if carrier.times_practiced_in_events == 0:
        gaps.append("No events practice this knowledge")
    if carrier.times_built_into_habits == 0:
        gaps.append("Not built into any habits")
    if carrier.journal_reflections_count == 0:
        gaps.append("No journal reflections")
    if carrier.choices_informed_count == 0:
        gaps.append("Has not informed any choices/decisions")
    return gaps


def _was_once_substantiated(carrier: SubstanceCarrier) -> bool:
    """Check if knowledge was once practiced enough to warrant review tracking."""
    return (
        carrier.times_applied_in_tasks > 2
        or carrier.times_practiced_in_events > 1
        or carrier.times_built_into_habits > 0
    )


def needs_review(carrier: SubstanceCarrier) -> bool:
    """Spaced repetition: once-substantiated knowledge decayed below 0.5."""
    return calculate_substance_score(carrier) < 0.5 and _was_once_substantiated(carrier)


def days_until_review_needed(carrier: SubstanceCarrier) -> int | None:
    """Predict when substance drops below 0.5, or None if never substantiated."""
    if not _was_once_substantiated(carrier):
        return None

    current_score = calculate_substance_score(carrier)
    if current_score < 0.5:
        return 0

    activity_dates = [
        d
        for d in [
            carrier.last_applied_date,
            carrier.last_practiced_date,
            carrier.last_built_into_habit_date,
            carrier.last_reflected_date,
            carrier.last_choice_informed_date,
        ]
        if d is not None
    ]
    if not activity_dates:
        return 0

    most_recent_date = max(activity_dates)
    threshold_days = -HALF_LIFE_DAYS * log(0.5)  # ~21 days
    days_since_use = (datetime.now() - most_recent_date).days
    return max(0, int(threshold_days - days_since_use))


def get_substantiation_summary(carrier: SubstanceCarrier) -> dict[str, Any]:
    """Comprehensive substantiation summary for UI display."""
    score = calculate_substance_score(carrier)
    gaps = get_substantiation_gaps(carrier)

    task_progress = min(1.0, (carrier.times_applied_in_tasks * TASK_WEIGHT) / TASK_CAP)
    event_progress = min(1.0, (carrier.times_practiced_in_events * EVENT_WEIGHT) / EVENT_CAP)
    habit_progress = min(1.0, (carrier.times_built_into_habits * HABIT_WEIGHT) / HABIT_CAP)
    journal_progress = min(1.0, (carrier.journal_reflections_count * JOURNAL_WEIGHT) / JOURNAL_CAP)
    choice_progress = min(1.0, (carrier.choices_informed_count * CHOICE_WEIGHT) / CHOICE_CAP)

    recommendations = []
    if "No tasks apply this knowledge" in gaps:
        recommendations.append(
            {
                "type": "task",
                "message": f"Create a task that applies: {carrier.title}",
                "impact": f"+{TASK_WEIGHT} substance per task (max +{TASK_CAP})",
            }
        )
    if "Not built into any habits" in gaps:
        recommendations.append(
            {
                "type": "habit",
                "message": f"Build a habit around: {carrier.title}",
                "impact": f"+{HABIT_WEIGHT} substance per habit (max +{HABIT_CAP})",
            }
        )
    if "No journal reflections" in gaps:
        recommendations.append(
            {
                "type": "journal",
                "message": f"Reflect on your experience with: {carrier.title}",
                "impact": f"+{JOURNAL_WEIGHT} substance per reflection (max +{JOURNAL_CAP})",
            }
        )

    if score >= 0.7:
        status = "Well practiced! Keep it up."
    elif score >= 0.5:
        status = "Solid foundation. Practice more to deepen mastery."
    elif score >= 0.3:
        status = "Applied but not yet integrated. Build habits."
    elif score > 0:
        status = "Theoretical knowledge. Apply in projects."
    else:
        status = "Pure theory. Create tasks and practice."

    return {
        "substance_score": round(score, 2),
        "breakdown": {
            "tasks": {
                "count": carrier.times_applied_in_tasks,
                "progress": round(task_progress, 2),
                "max_score": TASK_CAP,
            },
            "events": {
                "count": carrier.times_practiced_in_events,
                "progress": round(event_progress, 2),
                "max_score": EVENT_CAP,
            },
            "habits": {
                "count": carrier.times_built_into_habits,
                "progress": round(habit_progress, 2),
                "max_score": HABIT_CAP,
            },
            "journals": {
                "count": carrier.journal_reflections_count,
                "progress": round(journal_progress, 2),
                "max_score": JOURNAL_CAP,
            },
            "choices": {
                "count": carrier.choices_informed_count,
                "progress": round(choice_progress, 2),
                "max_score": CHOICE_CAP,
            },
        },
        "gaps": gaps,
        "review_status": {
            "needs_review": needs_review(carrier),
            "days_until_review": days_until_review_needed(carrier),
        },
        "recommendations": recommendations,
        "status_message": status,
        "is_theoretical_only": is_theoretical_only(carrier),
        "is_well_practiced": is_well_practiced(carrier),
    }
