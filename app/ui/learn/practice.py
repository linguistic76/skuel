"""Practice view — the learning loop.

Exercise → Submission → Report → Revised Exercise → repeat.

This page surfaces whichever phase the learner is in:
- Available exercises to start
- Active submissions (work in progress)
- Reports awaiting review (feedback received)
- Revised exercises (practice again)
"""

from fasthtml.common import A, Div, H2, H3, P, Span

from core.services.user.unified_user_context import UserContext


def PracticeView(context: UserContext) -> Div:
    """Practice page content — the learning loop at a glance."""
    return Div(
        Div(
            H2("Practice", cls="text-xl font-semibold text-base-content"),
            P(
                "Complete exercises, submit work, receive feedback, revise.",
                cls="text-sm text-base-content/50 mt-0.5",
            ),
            cls="mb-6",
        ),
        Div(
            _exercises_section(),
            _submissions_section(),
            _feedback_section(),
            _revisions_section(),
            cls="space-y-6",
        ),
    )


def _exercises_section() -> Div:
    """Available exercises to practice."""
    return Div(
        Div(
            Span("📝", cls="text-lg mr-2"),
            H3("Exercises", cls="text-base font-semibold text-base-content inline"),
            cls="flex items-center mb-3",
        ),
        P(
            "Browse available exercises based on articles you've studied.",
            cls="text-sm text-base-content/60 mb-3",
        ),
        A(
            "Browse exercises →",
            href="/exercises",
            cls="text-sm text-primary hover:underline",
        ),
        cls="bg-base-100 rounded-xl p-5 shadow-sm",
    )


def _submissions_section() -> Div:
    """Active submissions — work in progress."""
    return Div(
        Div(
            Span("📄", cls="text-lg mr-2"),
            H3("My Work", cls="text-base font-semibold text-base-content inline"),
            cls="flex items-center mb-3",
        ),
        P(
            "Submissions in progress and completed work.",
            cls="text-sm text-base-content/60 mb-3",
        ),
        A(
            "View submissions →",
            href="/submissions",
            cls="text-sm text-primary hover:underline",
        ),
        cls="bg-base-100 rounded-xl p-5 shadow-sm",
    )


def _feedback_section() -> Div:
    """Reports — feedback on submissions."""
    return Div(
        Div(
            Span("💬", cls="text-lg mr-2"),
            H3("Feedback", cls="text-base font-semibold text-base-content inline"),
            cls="flex items-center mb-3",
        ),
        P(
            "Reports and assessments on your submitted work.",
            cls="text-sm text-base-content/60 mb-3",
        ),
        A(
            "View feedback →",
            href="/submissions/reports",
            cls="text-sm text-primary hover:underline",
        ),
        cls="bg-base-100 rounded-xl p-5 shadow-sm",
    )


def _revisions_section() -> Div:
    """Revised exercises — practice again with targeted guidance."""
    return Div(
        Div(
            Span("🔄", cls="text-lg mr-2"),
            H3("Revisions", cls="text-base font-semibold text-base-content inline"),
            cls="flex items-center mb-3",
        ),
        P(
            "Targeted revision exercises based on your feedback. Practice again to strengthen understanding.",
            cls="text-sm text-base-content/60 mb-3",
        ),
        A(
            "View revisions →",
            href="/revised-exercises",
            cls="text-sm text-primary hover:underline",
        ),
        cls="bg-base-100 rounded-xl p-5 shadow-sm",
    )
