"""Learning dashboard — /learn landing page.

Workspace hub with 6 action cards (Exercises, Submit, My Submissions, Exercise Reports,
Activity Reports, Generate Reports) and curriculum discovery links.
No sidebar on the landing page.
"""

from fasthtml.common import H3, A, Div, P, Span

from core.services.user.unified_user_context import UserContext


def LearnDashboardView(context: UserContext) -> Div:
    """Landing page content for /learn — the student workspace hub."""
    return Div(
        Div(
            _exercises_card(),
            _submit_card(),
            _submissions_card(context),
            _exercise_reports_card(),
            _activity_reports_card(),
            _generate_reports_card(),
            cls="flex flex-col gap-5",
        ),
        Div(
            H3(
                "Curriculum",
                cls="text-base font-semibold text-base-content/80 mb-4",
            ),
            Div(
                _discovery_link("Articles", "/articles", "Browse teaching content"),
                _discovery_link("Knowledge Units", "/ku", "Explore atomic concepts"),
                _discovery_link("Learning Paths", "/pathways", "Structured progression"),
                cls="grid grid-cols-1 md:grid-cols-3 gap-3",
            ),
        ),
    )


def _submit_card() -> Div:
    """Submit Work card."""
    return Div(
        Div(
            Span("📤", cls="text-2xl"),
            H3("Submit Work", cls="text-lg font-semibold text-base-content"),
            cls="flex items-center gap-2 mb-3",
        ),
        P(
            "Upload files linked to exercises or knowledge units for review.",
            cls="text-sm text-base-content/60 mb-3",
        ),
        A(
            "Submit work →",
            href="/learn/submit",
            cls="text-sm text-primary hover:underline inline-block",
        ),
        cls="bg-base-100 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
    )


def _exercises_card() -> Div:
    """Exercises card."""
    return Div(
        Div(
            Span("🏋️", cls="text-2xl"),
            H3("Exercises", cls="text-lg font-semibold text-base-content"),
            cls="flex items-center gap-2 mb-3",
        ),
        P(
            "Practice with exercises linked to articles and knowledge units.",
            cls="text-sm text-base-content/60 mb-3",
        ),
        A(
            "Browse exercises →",
            href="/ui/exercises",
            cls="text-sm text-primary hover:underline inline-block",
        ),
        cls="bg-base-100 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
    )


def _submissions_card(context: UserContext) -> Div:
    """My Submissions card."""
    return Div(
        Div(
            Span("📝", cls="text-2xl"),
            H3("My Submissions", cls="text-lg font-semibold text-base-content"),
            cls="flex items-center gap-2 mb-3",
        ),
        P(
            "Track your submitted work and review status.",
            cls="text-sm text-base-content/60 mb-3",
        ),
        A(
            "View submissions →",
            href="/learn/submissions",
            cls="text-sm text-primary hover:underline inline-block",
        ),
        cls="bg-base-100 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
    )


def _exercise_reports_card() -> Div:
    """Exercise Reports card."""
    return Div(
        Div(
            Span("📋", cls="text-2xl"),
            H3("Exercise Reports", cls="text-lg font-semibold text-base-content"),
            cls="flex items-center gap-2 mb-3",
        ),
        P(
            "Teacher and AI feedback on your exercise submissions.",
            cls="text-sm text-base-content/60 mb-3",
        ),
        A(
            "View exercise reports →",
            href="/learn/exercise-reports",
            cls="text-sm text-primary hover:underline inline-block",
        ),
        cls="bg-base-100 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
    )


def _activity_reports_card() -> Div:
    """Activity Reports card."""
    return Div(
        Div(
            Span("📊", cls="text-2xl"),
            H3("Activity Reports", cls="text-lg font-semibold text-base-content"),
            cls="flex items-center gap-2 mb-3",
        ),
        P(
            "Activity feedback and progress reports across your domains.",
            cls="text-sm text-base-content/60 mb-3",
        ),
        A(
            "View activity reports →",
            href="/learn/activity-reports",
            cls="text-sm text-primary hover:underline inline-block",
        ),
        cls="bg-base-100 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
    )


def _generate_reports_card() -> Div:
    """Generate Reports card."""
    return Div(
        Div(
            Span("⚡", cls="text-2xl"),
            H3("Generate Reports", cls="text-lg font-semibold text-base-content"),
            cls="flex items-center gap-2 mb-3",
        ),
        P(
            "Create on-demand progress reports across your activity domains.",
            cls="text-sm text-base-content/60 mb-3",
        ),
        A(
            "Generate reports →",
            href="/learn/generate-reports",
            cls="text-sm text-primary hover:underline inline-block",
        ),
        cls="bg-base-100 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
    )


def _discovery_link(title: str, href: str, description: str) -> Div:
    """Curriculum discovery link card."""
    return A(
        Div(
            P(title, cls="font-semibold text-sm text-base-content"),
            P(description, cls="text-xs text-base-content/50 mt-0.5"),
            cls="bg-base-100 rounded-lg p-4 shadow-sm hover:shadow-md transition-shadow",
        ),
        href=href,
        cls="no-underline",
    )
