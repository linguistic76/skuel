"""Learning dashboard — /learn landing page.

Shows learning status at a glance: what to study, what to practice, pending feedback.
No sidebar on the landing page.
"""

from fasthtml.common import H2, H3, A, Div, P, Span

from core.services.user.unified_user_context import UserContext


def LearnDashboardView(context: UserContext) -> Div:
    """Landing page content for /learn.

    Shows three cards corresponding to the sidebar sections:
    Study, Practice, Pathways — each with a quick status summary.
    """
    return Div(
        _header(),
        Div(
            _study_card(context),
            _practice_card(context),
            _pathways_card(context),
            cls="grid grid-cols-1 md:grid-cols-3 gap-5",
        ),
    )


def _header() -> Div:
    return Div(
        H2("Learn", cls="text-xl font-semibold text-base-content"),
        P(
            "Study content, practice with exercises, track your progress.",
            cls="text-sm text-base-content/50 mt-0.5",
        ),
        cls="mb-6",
    )


def _study_card(context: UserContext) -> Div:
    """Study card — Articles and Knowledge Units."""
    total = len(context.mastered_knowledge_uids) + len(context.in_progress_knowledge_uids)
    mastered = len(context.mastered_knowledge_uids)

    return Div(
        Div(
            Span("📖", cls="text-2xl"),
            H3("Study", cls="text-lg font-semibold text-base-content"),
            cls="flex items-center gap-2 mb-3",
        ),
        P(
            f"{total} articles explored"
            if total > 0
            else "Start exploring articles and knowledge units.",
            cls="text-sm text-base-content/60 mb-2",
        ),
        P(
            f"{mastered} mastered",
            cls="text-xs text-base-content/40",
        )
        if mastered > 0
        else None,
        A(
            "Browse articles →",
            href="/learn/study",
            cls="text-sm text-primary hover:underline mt-3 inline-block",
        ),
        cls="bg-base-100 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
    )


def _practice_card(context: UserContext) -> Div:
    """Practice card — the learning loop status."""
    return Div(
        Div(
            Span("✏️", cls="text-2xl"),
            H3("Practice", cls="text-lg font-semibold text-base-content"),
            cls="flex items-center gap-2 mb-3",
        ),
        P(
            "Complete exercises, submit work, receive feedback.",
            cls="text-sm text-base-content/60 mb-2",
        ),
        A(
            "View practice →",
            href="/learn/practice",
            cls="text-sm text-primary hover:underline mt-3 inline-block",
        ),
        cls="bg-base-100 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
    )


def _pathways_card(context: UserContext) -> Div:
    """Pathways card — structured learning progression."""
    enrolled = len(context.enrolled_path_uids) if context.enrolled_path_uids else 0

    return Div(
        Div(
            Span("🗺️", cls="text-2xl"),
            H3("Pathways", cls="text-lg font-semibold text-base-content"),
            cls="flex items-center gap-2 mb-3",
        ),
        P(
            f"{enrolled} learning path{'s' if enrolled != 1 else ''} enrolled"
            if enrolled > 0
            else "Structured sequences to guide your learning.",
            cls="text-sm text-base-content/60 mb-2",
        ),
        A(
            "Browse pathways →",
            href="/learn/pathways",
            cls="text-sm text-primary hover:underline mt-3 inline-block",
        ),
        cls="bg-base-100 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
    )
