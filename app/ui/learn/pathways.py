"""Pathways view — structured learning progression.

Learning Paths + Steps for guided curriculum navigation.
Links into existing pathways routes for detailed views.
"""

from fasthtml.common import A, Div, H2, P, Span

from core.services.user.unified_user_context import UserContext


def PathwaysView(context: UserContext) -> Div:
    """Pathways page content — learning paths and steps."""
    enrolled = len(context.enrolled_learning_paths) if context.enrolled_learning_paths else 0

    return Div(
        Div(
            H2("Pathways", cls="text-xl font-semibold text-base-content"),
            P(
                "Structured sequences to guide your learning.",
                cls="text-sm text-base-content/50 mt-0.5",
            ),
            cls="mb-6",
        ),
        # Stats
        Div(
            _stat_card("🗺️", "Enrolled", str(enrolled)),
            cls="grid grid-cols-3 gap-4 mb-6",
        ),
        # Quick links to existing pathways
        Div(
            A(
                Span("🗺️", cls="mr-2"),
                "Browse Pathways",
                href="/pathways",
                cls="btn btn-primary btn-sm",
            ),
            cls="flex gap-3",
        ),
    )


def _stat_card(icon: str, label: str, value: str) -> Div:
    return Div(
        Span(icon, cls="text-xl mb-1"),
        Div(value, cls="text-2xl font-bold text-base-content"),
        Div(label, cls="text-xs text-base-content/50"),
        cls="bg-base-100 rounded-lg p-4 text-center shadow-sm",
    )
