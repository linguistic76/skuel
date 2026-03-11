"""Study view — browse Articles and Knowledge Units.

This is the content discovery page under /learn/study.
Links into existing Article and KU routes for detailed views.
"""

from fasthtml.common import H2, A, Div, P, Span

from core.services.user.unified_user_context import UserContext


def StudyView(context: UserContext) -> Div:
    """Study page content — articles and knowledge units to engage with."""
    total = len(context.mastered_knowledge_uids) + len(context.in_progress_knowledge_uids)
    mastered = len(context.mastered_knowledge_uids)
    in_progress = len(context.in_progress_knowledge_uids)

    return Div(
        Div(
            H2("Study", cls="text-xl font-semibold text-base-content"),
            P(
                "Articles and knowledge units to explore.",
                cls="text-sm text-base-content/50 mt-0.5",
            ),
            cls="mb-6",
        ),
        # Stats summary
        Div(
            _stat_card("📖", "Total Explored", str(total)),
            _stat_card("✅", "Mastered", str(mastered)),
            _stat_card("📝", "In Progress", str(in_progress)),
            cls="grid grid-cols-3 gap-4 mb-6",
        ),
        # Quick links to existing article browsing
        Div(
            A(
                Span("📚", cls="mr-2"),
                "Browse Knowledge Hub",
                href="/ku",
                cls="btn btn-primary btn-sm",
            ),
            A(
                Span("🔍", cls="mr-2"),
                "Discovery",
                href="/article/discovery",
                cls="btn btn-ghost btn-sm",
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
