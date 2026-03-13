"""Curriculum domain view components for profile page.

Covers: KU (Knowledge Units), LS (Learning Steps), LP (Learning Paths).

See: /docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
"""

from typing import Any

from fasthtml.common import H2, H3, A, Div, P, Span

from core.services.user.unified_user_context import UserContext
from ui.patterns.empty_state import EmptyState


def KnowledgeDomainView(context: UserContext, services: Any = None, user_uid: str = "") -> Div:
    """Knowledge domain: all KUs with user's VIEWED/BOOKMARKED status.

    Queries Neo4j for all Entity nodes and enriches with per-user relationships.

    Args:
        context: UserContext (used for mastered/in_progress status)
        services: Services container (for Neo4j driver access)
        user_uid: Current user's UID (for relationship queries)
    """
    # The KU list is populated via the route handler which queries Neo4j
    # This view is a placeholder that expects ku_items to be passed via
    # the route handler wrapping this in a Div
    mastered = len(context.mastered_knowledge_uids)
    in_progress = len(context.in_progress_knowledge_uids)
    ready = len(context.ready_to_learn_uids)

    return Div(
        H2("Knowledge Units", cls="text-2xl font-bold mb-2"),
        P(
            "All knowledge units in the curriculum. Track your learning progress.",
            cls="text-muted-foreground mb-6",
        ),
        # Quick stats row
        Div(
            Div(
                Span(str(mastered), cls="text-xl font-bold text-success"),
                Span(" mastered", cls="text-sm text-muted-foreground"),
                cls="flex items-baseline gap-1",
            ),
            Div(
                Span(str(in_progress), cls="text-xl font-bold text-warning"),
                Span(" in progress", cls="text-sm text-muted-foreground"),
                cls="flex items-baseline gap-1",
            ),
            Div(
                Span(str(ready), cls="text-xl font-bold text-info"),
                Span(" ready", cls="text-sm text-muted-foreground"),
                cls="flex items-baseline gap-1",
            ),
            cls="flex gap-6 mb-6",
        ),
        # KU list placeholder - actual items injected by route handler
        Div(id="ku-list-content"),
        # Link to main KU listing
        A(
            "Browse All Knowledge →",
            href="/knowledge",
            cls="inline-block mt-4 text-primary hover:text-primary-hover font-medium",
        ),
    )


def LearningStepsDomainView(_context: UserContext, _focus_uid: str | None = None) -> Div:
    """Learning Steps domain: placeholder for LS nodes (not yet created).

    Shows a clean empty state explaining what learning steps are.
    """
    return Div(
        H2("Learning Steps", cls="text-2xl font-bold mb-2"),
        P(
            "Structured sequences within a learning path.",
            cls="text-muted-foreground mb-6",
        ),
        EmptyState(
            title="No learning steps available yet",
            description=(
                "Learning steps are ordered sequences of Knowledge Units "
                "within a Learning Path. They provide structured, teacher-directed "
                "curriculum progression."
            ),
            action_text="Explore Knowledge Units →",
            action_href="/knowledge",
            icon="📝",
        ),
    )


def LearningPathsDomainView(context: UserContext, focus_uid: str | None = None) -> Div:
    """Learning Paths domain: enrolled paths with progress + ready to learn.

    Shows:
    - Active learning paths with progress
    - Knowledge ready to learn (prerequisites met)
    """
    # , Task 11: Add "Back to Insights" link if coming from insights
    back_link = Div()
    if focus_uid:
        back_link = Div(
            A(
                "← Back to Insights",
                href="/insights",
                cls="inline-block mb-4 text-sm text-primary hover:text-primary-hover",
            ),
            cls="mb-2",
        )

    return Div(
        back_link,
        H2("Learning Paths", cls="text-2xl font-bold mb-2"),
        P(
            "Structured learning journeys through the curriculum.",
            cls="text-muted-foreground mb-6",
        ),
        # Learning Paths section
        H3("Your Paths", cls="text-lg font-semibold text-foreground mt-2 mb-4"),
        _learning_paths_list(context),
        # Ready to Learn section
        H3("Ready to Learn", cls="text-lg font-semibold text-foreground mt-6 mb-4"),
        _ready_to_learn_list(context),
        # Link to knowledge page
        A(
            "Browse Knowledge →",
            href="/knowledge",
            cls="inline-block mt-4 text-primary hover:text-primary-hover font-medium",
        ),
    )


def _learning_paths_list(context: UserContext) -> Div:
    """List of enrolled learning paths with progress."""
    if not context.enrolled_paths_rich:
        if not context.enrolled_path_uids:
            return EmptyState("No learning paths enrolled")
        # Fallback if no rich data
        items = [
            Div(
                Span("🗺️", cls="mr-2"),
                Span(f"Path {uid[:12]}...", cls="font-medium text-foreground"),
                cls="flex items-center p-3 bg-background rounded-lg",
            )
            for uid in context.enrolled_path_uids[:5]
        ]
        return Div(*items, cls="space-y-2")

    # Build items from rich data
    items = []
    for path_data in context.enrolled_paths_rich[:5]:
        path = path_data.get("path", {})
        graph_context = path_data.get("graph_context", {})

        title = path.get("title", "Learning Path")
        uid = path.get("uid", "")
        progress = graph_context.get("progress", 0.0)
        progress_percent = int(progress * 100)

        # Determine if this is the current focus path
        is_current = uid == context.current_learning_path_uid

        items.append(
            A(
                Div(
                    Div(
                        Span("🗺️", cls="mr-2"),
                        Span(title, cls="font-medium text-foreground flex-1"),
                        Span(
                            "Active" if is_current else "",
                            cls="text-xs text-primary font-medium",
                        )
                        if is_current
                        else None,
                        cls="flex items-center mb-2",
                    ),
                    # Progress bar
                    Div(
                        Div(
                            cls="h-2 bg-primary rounded-full transition-all",
                            style=f"width: {progress_percent}%",
                        ),
                        cls="h-2 bg-muted rounded-full w-full",
                    ),
                    Div(
                        Span(f"{progress_percent}% complete", cls="text-xs text-muted-foreground"),
                        cls="mt-1",
                    ),
                    cls="w-full",
                ),
                href=f"/pathways/path/{uid}" if uid else "#",
                cls="block p-3 bg-background rounded-lg hover:bg-muted transition-colors",
            )
        )

    return Div(*items, cls="space-y-2") if items else EmptyState("No learning paths enrolled")


def _ready_to_learn_list(context: UserContext) -> Div:
    """List of knowledge units ready to learn (prerequisites met)."""
    ready_uids = list(context.ready_to_learn_uids)[:5]

    if not ready_uids:
        # Check if there are blocked items
        if context.prerequisites_needed:
            blocked_count = len(context.prerequisites_needed)
            return Div(
                P(
                    f"{blocked_count} knowledge units blocked by prerequisites",
                    cls="text-muted-foreground text-sm",
                ),
                P(
                    "Complete prerequisite knowledge to unlock more",
                    cls="text-muted-foreground text-xs mt-1",
                ),
                cls="bg-muted rounded-lg p-4",
            )
        return EmptyState("No knowledge ready to learn")

    # Try to get titles from knowledge_units_rich if available
    items = []
    for uid in ready_uids:
        ku_data = context.knowledge_units_rich.get(uid, {})
        ku = ku_data.get("ku", {})
        title = ku.get("title", uid) if ku else uid

        items.append(
            A(
                Span("💡", cls="mr-2"),
                Span(title, cls="font-medium text-foreground"),
                href=f"/article/{uid}",
                cls="flex items-center p-3 bg-background rounded-lg hover:bg-muted transition-colors",
            )
        )

    return Div(*items, cls="space-y-2")
