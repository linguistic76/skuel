"""Profile hub page — THE main hub, grouped card grid (MOC pattern).

The /profile page is the top-level entry point. Cards link directly to
domain hub pages (KU, Lessons, Submissions, Reports). Uses BasePage(STANDARD).

See: /docs/patterns/HUB_PAGE_PATTERN.md
"""

from fasthtml.common import Div, Span

from core.services.user.unified_user_context import UserContext
from ui.patterns.hub import HubCardData, HubSection


def ProfileHubView(context: UserContext) -> Div:
    """Profile hub — Focus/Velocity header + grouped card grid."""
    return Div(
        _personal_header(context),
        HubSection("Knowledge", _knowledge_cards(context)),
        HubSection("Practice", _practice_cards(context)),
        HubSection("Reports", _reports_cards(context)),
        _settings_link(),
    )


# ---------------------------------------------------------------------------
# Card definitions — context-driven with optional badges
# ---------------------------------------------------------------------------


def _knowledge_cards(context: UserContext) -> list[HubCardData]:
    return [
        HubCardData(
            "\U0001f4d6",
            "Knowledge",
            "/ku",
            "Atomic knowledge units \u2014 concepts, facts, vocabulary.",
            badge=len(context.ku_bookmarked_uids) or None,
        ),
        HubCardData(
            "\U0001f4da",
            "Lessons",
            "/lessons",
            "Learning content that composes atomic knowledge.",
        ),
    ]


def _practice_cards(context: UserContext) -> list[HubCardData]:
    return [
        HubCardData(
            "\U0001f3cb\ufe0f",
            "Exercises",
            "/exercises",
            "Practice linked to lessons and knowledge units.",
            badge=context.assigned_exercise_count or None,
        ),
        HubCardData(
            "\U0001f4e4",
            "Submit Work",
            "/submit",
            "Upload submissions for review.",
            badge=len(context.unsubmitted_exercises) or None,
        ),
        HubCardData(
            "\U0001f4dd",
            "Submissions",
            "/submissions",
            "Track submitted work and review status.",
            badge=context.total_submission_count or None,
        ),
    ]


def _reports_cards(context: UserContext) -> list[HubCardData]:
    return [
        HubCardData(
            "\U0001f4cb",
            "Exercise Reports",
            "/exercise-reports",
            "Teacher and AI feedback on submissions.",
            badge=context.pending_feedback_count or None,
        ),
        HubCardData(
            "\U0001f4ca",
            "Activity Reports",
            "/activity-reports",
            "Progress reports across domains.",
        ),
    ]


# ---------------------------------------------------------------------------
# Personal header — Focus + Velocity
# ---------------------------------------------------------------------------


def _personal_header(context: UserContext) -> Div:
    """Focus + Velocity compact header."""
    return Div(_focus_line(context), _velocity_line(context), cls="mb-2")


def _focus_line(context: UserContext) -> Div:
    """Current task focus — compact inline."""
    if not context.current_task_focus:
        return Div(
            Span("\U0001f3af", cls="text-lg mr-2"),
            Span("No current focus set", cls="text-sm text-muted-foreground"),
            cls="flex items-center mb-2",
        )

    task_title = "Current Task"
    for task_data in context.entities_rich.get("tasks", []):
        task = task_data.get("entity", {})
        if task.get("uid") == context.current_task_focus:
            task_title = task.get("title", "Current Task")
            break

    return Div(
        Span("\U0001f3af", cls="text-lg mr-2"),
        Span("Focus: ", cls="text-sm font-medium text-muted-foreground"),
        Span(task_title, cls="text-sm font-medium text-primary"),
        cls="flex items-center mb-2",
    )


def _velocity_line(context: UserContext) -> Div:
    """Overall velocity — compact inline indicator."""
    total_velocity = sum(context.velocity_by_domain.values())
    total_time = sum(context.time_invested_hours_by_domain.values())

    if total_velocity > 0.5:
        icon, label, color = "\U0001f680", "Strong Momentum", "text-success"
    elif total_velocity > 0:
        icon, label, color = "\U0001f4c8", "Building", "text-primary"
    elif total_velocity > -0.3:
        icon, label, color = "\u27a1\ufe0f", "Steady", "text-muted-foreground"
    else:
        icon, label, color = "\U0001f4c9", "Slowing", "text-warning"

    return Div(
        Span(icon, cls="text-lg mr-2"),
        Span(label, cls=f"text-sm font-medium {color}"),
        Span(" \u00b7 ", cls="text-foreground/30 mx-2"),
        Span(f"{total_time:.1f}h invested", cls="text-sm text-muted-foreground"),
        cls="flex items-center mb-4",
    )


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------


def _settings_link() -> Div:
    """Compact settings link at the bottom."""
    from fasthtml.common import A

    return Div(
        A(
            Span("\u2699\ufe0f", cls="mr-2"),
            "Settings",
            href="/profile/settings",
            cls="text-sm text-muted-foreground hover:text-foreground",
        ),
        cls="mt-4 pt-6 border-t border-border",
    )
