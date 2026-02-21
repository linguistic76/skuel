"""
Knowledge Substance Dashboard Components
==========================================

UI components for visualizing knowledge substance tracking.

Philosophical Foundation:
"Applied knowledge, not pure theory" - Shows how knowledge is used in real life.

Components:
- SubstanceScoreCard: Main substance score with status
- SubstanceBreakdownCard: Detailed breakdown by type
- SubstanceRecommendationsCard: Actionable practice recommendations
- SubstanceReviewCard: Spaced repetition review schedule
- FullSubstanceDashboard: Complete dashboard (all components)

Usage:
    from ui.substance_dashboard import (
        SubstanceScoreCard,
        FullSubstanceDashboard
    )

    # In route
    ku = await ku_service.get("ku.python.basics")
    summary = ku.get_substantiation_summary()

    return Div(
        FullSubstanceDashboard(summary, ku.title),
        ...
    )
"""

from typing import Any

from fasthtml.common import H3, H4, P

from ui.daisy_components import Button, Card, CardBody, Div, Progress, ProgressT, Span
from ui.shared_components import (
    StatusBadge,
)

# ============================================================================
# SUBSTANCE SCORE CARD
# ============================================================================


def SubstanceScoreCard(
    score: float,
    title: str,
    status_message: str | None = None,
    _is_theoretical: bool = False,
    _is_well_practiced: bool = False,
) -> Any:
    """
    Display main substance score with visual indicator and status.

    Args:
        score: Substance score (0.0 to 1.0),
        title: Knowledge unit title,
        status_message: Human-readable status ("Mastered!", "Needs practice", etc.),
        is_theoretical: True if score < 0.2 (pure theory),
        is_well_practiced: True if score >= 0.7 (deeply integrated)

    Returns:
        Card component with substance score,

    Example:
        >>> SubstanceScoreCard(
        ...     score=0.68,
        ...     title="Python Functions",
        ...     status_message="Well practiced! Keep it up.",
        ...     is_well_practiced=True,
        ... )
    """
    # Determine color and icon based on score
    if score >= 0.8:
        color = "green"
        icon = "🏆"
        badge_text = "MASTERED"
    elif score >= 0.7:
        color = "blue"
        icon = "✅"
        badge_text = "WELL PRACTICED"
    elif score >= 0.5:
        color = "yellow"
        icon = "📚"
        badge_text = "SOLID FOUNDATION"
    elif score >= 0.3:
        color = "orange"
        icon = "⚠️"
        badge_text = "APPLIED"
    elif score > 0:
        color = "red"
        icon = "📖"
        badge_text = "THEORETICAL"
    else:
        color = "gray"
        icon = "❓"
        badge_text = "PURE THEORY"

    percentage = f"{score * 100:.0f}%"

    # Map color names to ProgressT variants
    progress_variant = {
        "green": ProgressT.success,
        "blue": ProgressT.info,
        "yellow": ProgressT.warning,
        "orange": ProgressT.warning,
        "red": ProgressT.error,
        "gray": ProgressT.primary,
    }.get(color, ProgressT.primary)

    return Card(
        CardBody(
            Div(
                Div(
                    P("Substance Score", cls="text-sm text-gray-600 mb-1"),
                    H3(f"{icon} {percentage}", cls=f"text-4xl font-bold text-{color}-600 mb-2"),
                    P(title, cls="text-lg font-medium text-gray-700 mb-2"),
                    P(status_message, cls="text-sm text-gray-600 italic")
                    if status_message
                    else None,
                ),
                StatusBadge(badge_text, color),
                cls="flex justify-between items-start mb-4",
            ),
            # Visual progress bar
            Progress(value=int(score * 100), variant=progress_variant, cls="h-3"),
            # Explanation text
            Div(
                P(
                    "Substance measures how well knowledge is applied in real life. "
                    "Pure theory = 0%, Lifestyle-integrated = 100%.",
                    cls="text-gray-700",
                ),
                cls="mt-4 p-3 bg-gray-50 rounded text-sm",
            ),
        ),
        cls=f"border-l-4 border-{color}-500",
    )


# ============================================================================
# SUBSTANCE BREAKDOWN CARD
# ============================================================================


def SubstanceBreakdownCard(breakdown: dict[str, Any]) -> Any:
    """
    Display detailed breakdown of substance by type.

    Args:
        breakdown: Breakdown data from ku.get_substantiation_summary()
            Structure:
            {
                'tasks': {'count': 5, 'progress': 1.0, 'max_score': 0.25},
                'events': {'count': 3, 'progress': 0.60, 'max_score': 0.25},
                'habits': {'count': 1, 'progress': 0.33, 'max_score': 0.30},
                'journals': {'count': 0, 'progress': 0.0, 'max_score': 0.20},
                'choices': {'count': 0, 'progress': 0.0, 'max_score': 0.15}
            }

    Returns:
        Card component with breakdown visualization,

    Example:
        >>> summary = ku.get_substantiation_summary()
        >>> SubstanceBreakdownCard(summary["breakdown"])
    """
    return Card(
        CardBody(
            H4("📊 Substance Breakdown", cls="text-lg font-semibold text-gray-800 mb-4"),
            # Tasks
            Div(
                Div(
                    Span(
                        f"✓ Applied in {breakdown['tasks']['count']} tasks",
                        cls="font-medium text-gray-700",
                    ),
                    Span(
                        f"{breakdown['tasks']['progress'] * 100:.0f}% of max (0.25)",
                        cls="text-sm text-gray-600",
                    ),
                    cls="flex justify-between mb-1",
                ),
                Progress(
                    value=int(breakdown["tasks"]["progress"] * 100),
                    variant=ProgressT.primary,
                    cls="h-2",
                ),
                cls="mb-4",
            ),
            # Events
            Div(
                Div(
                    Span(
                        f"📅 Practiced in {breakdown['events']['count']} events",
                        cls="font-medium text-gray-700",
                    ),
                    Span(
                        f"{breakdown['events']['progress'] * 100:.0f}% of max (0.25)",
                        cls="text-sm text-gray-600",
                    ),
                    cls="flex justify-between mb-1",
                ),
                Progress(
                    value=int(breakdown["events"]["progress"] * 100),
                    variant=ProgressT.secondary,
                    cls="h-2",
                ),
                cls="mb-4",
            ),
            # Habits (highest weight)
            Div(
                Div(
                    Span(
                        f"🔁 Built into {breakdown['habits']['count']} habits",
                        cls="font-medium text-gray-700",
                    ),
                    Span(
                        f"{breakdown['habits']['progress'] * 100:.0f}% of max (0.30) - Lifestyle Integration!",
                        cls="text-sm text-green-600 font-semibold",
                    ),
                    cls="flex justify-between mb-1",
                ),
                Progress(
                    value=int(breakdown["habits"]["progress"] * 100),
                    variant=ProgressT.success,
                    cls="h-2",
                ),
                cls="mb-4",
            ),
            # Journals (metacognition)
            Div(
                Div(
                    Span(
                        f"📝 Reflected in {breakdown['journals']['count']} journals",
                        cls="font-medium text-gray-700",
                    ),
                    Span(
                        f"{breakdown['journals']['progress'] * 100:.0f}% of max (0.20) - Metacognition",
                        cls="text-sm text-purple-600 font-semibold",
                    ),
                    cls="flex justify-between mb-1",
                ),
                Progress(
                    value=int(breakdown["journals"]["progress"] * 100),
                    variant=ProgressT.accent,
                    cls="h-2",
                ),
                cls="mb-4",
            ),
            # Choices (decision-making)
            Div(
                Div(
                    Span(
                        f"🎯 Informed {breakdown['choices']['count']} choices",
                        cls="font-medium text-gray-700",
                    ),
                    Span(
                        f"{breakdown['choices']['progress'] * 100:.0f}% of max (0.15) - Decision-Making",
                        cls="text-sm text-blue-600 font-semibold",
                    ),
                    cls="flex justify-between mb-1",
                ),
                Progress(
                    value=int(breakdown["choices"]["progress"] * 100),
                    variant=ProgressT.info,
                    cls="h-2",
                ),
                cls="mb-4",
            ),
            # Weighting explanation
            Div(
                P("💡 Weighting Strategy:", cls="text-blue-900 font-medium mb-1"),
                P(
                    "Habits (0.10) > Journals/Choices (0.07) > Tasks/Events (0.05). "
                    "Lifestyle integration and metacognition weigh more than practice alone.",
                    cls="text-blue-800 text-xs leading-relaxed",
                ),
                cls="mt-4 p-3 bg-blue-50 rounded text-sm",
            ),
        ),
    )


# ============================================================================
# SUBSTANCE RECOMMENDATIONS CARD
# ============================================================================


def SubstanceRecommendationsCard(
    gaps: list[str], recommendations: list[dict[str, str]], ku_uid: str
) -> Any:
    """
    Display actionable recommendations to increase substance.

    Args:
        gaps: List of gap descriptions,
        recommendations: List of recommendation dicts with:
            - type: "task", "habit", "journal", etc.
            - message: Recommendation text
            - impact: Impact description,
        ku_uid: Knowledge unit UID for action links

    Returns:
        Card component with recommendations,

    Example:
        >>> summary = ku.get_substantiation_summary()
        >>> SubstanceRecommendationsCard(
        ...     gaps=summary["gaps"],
        ...     recommendations=summary["recommendations"],
        ...     ku_uid="ku.python.basics",
        ... )
    """
    # Build gaps section
    gaps_section = None
    if gaps:
        gaps_section = Div(
            P(
                f"Missing Substantiation ({len(gaps)} types):",
                cls="text-sm font-medium text-gray-700 mb-2",
            ),
            Div(
                *[
                    Div(
                        Span("⚠", cls="text-yellow-500 mr-2"),
                        Span(gap),
                        cls="flex items-start text-sm text-gray-600",
                    )
                    for gap in gaps
                ],
                cls="space-y-1",
            ),
            cls="mb-4",
        )

    # Build recommendations section
    recs_section = None
    if recommendations:

        def get_rec_icon(rec_type: str) -> str:
            if rec_type == "task":
                return "✓"
            elif rec_type == "habit":
                return "🔁"
            return "📝"

        recs_section = Div(
            *[
                Div(
                    Div(
                        Span(get_rec_icon(rec["type"]), cls="text-xl mr-2"),
                        Div(
                            P(rec["message"], cls="text-gray-900 font-medium text-sm"),
                            P(rec["impact"], cls="text-xs text-green-600 mt-1"),
                            cls="flex-1",
                        ),
                        cls="flex items-start mb-2",
                    ),
                    Button(
                        f"Create {rec['type'].capitalize()}",
                        cls="btn btn-xs btn-primary mt-2",
                        hx_get=f"/knowledge/{ku_uid}/{rec['type']}/create",
                        hx_target="#modal",
                    ),
                    cls="p-3 border border-gray-200 rounded bg-gray-50",
                )
                for rec in recommendations[:3]  # Show top 3
            ],
            cls="mt-4 space-y-3",
        )

    # Build no recommendations section
    no_recs_section = None
    if not recommendations:
        no_recs_section = Div(
            P(
                "🎉 Excellent! Knowledge is well-substantiated across all types.",
                cls="text-gray-600 text-sm",
            ),
            cls="text-center py-4",
        )

    return Card(
        CardBody(
            H4("💡 Practice Recommendations", cls="text-lg font-semibold text-gray-800 mb-4"),
            gaps_section,
            recs_section,
            no_recs_section,
        ),
    )


# ============================================================================
# SUBSTANCE REVIEW CARD (SPACED REPETITION)
# ============================================================================


def SubstanceReviewCard(review_status: dict[str, Any]) -> Any:
    """
    Display spaced repetition review schedule.

    Args:
        review_status: Review status data:
            {
                'needs_review': bool,
                'days_until_review': int | None
            }

    Returns:
        Card component with review schedule,

    Example:
        >>> summary = ku.get_substantiation_summary()
        >>> SubstanceReviewCard(summary["review_status"])
    """
    needs_review = review_status.get("needs_review", False)
    days_until = review_status.get("days_until_review")

    if needs_review:
        color = "red"
        icon = "⏰"
        message = "Needs review NOW! Knowledge is decaying."
        action = "Schedule Review"
    elif days_until is not None and days_until <= 7:
        color = "yellow"
        icon = "📅"
        message = f"Review scheduled in {days_until} days (substance will decay to 50%)"
        action = "Review Early"
    elif days_until is not None:
        color = "green"
        icon = "✅"
        message = f"Next review in {days_until} days (spaced repetition)"
        action = "View Schedule"
    else:
        color = "gray"
        icon = "❓"
        message = "No review needed (knowledge never substantiated)"
        action = None

    return Card(
        CardBody(
            Div(
                Div(
                    H4(f"{icon} Review Schedule", cls="text-lg font-semibold text-gray-800 mb-1"),
                    P(message, cls="text-sm text-gray-700"),
                ),
                Button(action, cls=f"btn btn-sm btn-{color}") if action else None,
                cls="flex items-start justify-between mb-3",
            ),
            # Spaced repetition explanation
            Div(
                P("🧠 Spaced Repetition:", cls="text-purple-900 font-medium mb-1"),
                P(
                    "Knowledge decays exponentially (30-day half-life). "
                    "Regular review maintains substance above 50% threshold. "
                    "Practice before forgetting!",
                    cls="text-purple-800 text-xs leading-relaxed",
                ),
                cls="mt-4 p-3 bg-purple-50 rounded text-sm",
            ),
        ),
        cls=f"border-l-4 border-{color}-500",
    )


# ============================================================================
# FULL SUBSTANCE DASHBOARD
# ============================================================================


def FullSubstanceDashboard(summary: dict[str, Any], title: str, ku_uid: str | None = None) -> Div:
    """
    Complete substance tracking dashboard with all components.

    Args:
        summary: Complete summary from ku.get_substantiation_summary(),
        title: Knowledge unit title,
        ku_uid: Knowledge unit UID (for action buttons)

    Returns:
        Div with complete dashboard,

    Example:
        >>> ku = await ku_service.get("ku.python.basics")
        >>> summary = ku.get_substantiation_summary()
        >>> FullSubstanceDashboard(summary, ku.title, ku.uid)
    """
    # Build recommendations card conditionally
    recommendations_card = None
    if ku_uid:
        recommendations_card = SubstanceRecommendationsCard(
            gaps=summary.get("gaps", []),
            recommendations=summary.get("recommendations", []),
            ku_uid=ku_uid,
        )

    return Div(
        # Header
        H3(f"Knowledge Substance: {title}", cls="text-2xl font-bold text-gray-900 mb-4"),
        # Main score card
        SubstanceScoreCard(
            score=summary.get("substance_score", 0.0),
            title=title,
            status_message=summary.get("status_message"),
            _is_theoretical=summary.get("is_theoretical_only", False),
            _is_well_practiced=summary.get("is_well_practiced", False),
        ),
        # Breakdown and recommendations in grid
        Div(
            SubstanceBreakdownCard(summary.get("breakdown", {})),
            recommendations_card,
            cls="grid md:grid-cols-2 gap-6",
        ),
        # Review schedule
        SubstanceReviewCard(summary.get("review_status", {})),
        # Philosophical note
        Div(
            P(
                '"Applied knowledge, not pure theory" - SKUEL Knowledge Philosophy',
                cls="text-sm text-gray-800 italic text-center",
            ),
            cls="p-4 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg border border-blue-200",
        ),
        cls="space-y-6",
    )


# ============================================================================
# PUBLIC API
# ============================================================================

__all__ = [
    "FullSubstanceDashboard",
    "SubstanceBreakdownCard",
    "SubstanceRecommendationsCard",
    "SubstanceReviewCard",
    "SubstanceScoreCard",
]
