"""
Lesson UI Routes — Lesson-Specific UI Endpoints
================================================

Lesson detail views, creation forms, and fragment endpoints.
The /ku route has moved to ku_ui.py (served by KuService).
"""

from typing import Any

from fasthtml.common import H1, H2, H3, Div, Li, NotStr, P, Request, Span, Ul
from fasthtml.common import A as Anchor
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from core.utils.logging import get_logger
from core.utils.markdown_renderer import render_markdown_with_toc
from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.breadcrumbs import Breadcrumbs
from ui.patterns.card_generator import CardGenerator

logger = get_logger("skuel.routes.lesson.ui")


# ============================================================================
# UI COMPONENT LIBRARY - Reusable Lesson components
# ============================================================================


def _metadata_badge(label: str, value: str, variant: BadgeT = BadgeT.ghost) -> Any:
    """Render a metadata badge."""
    return Badge(
        Span(label, cls="font-medium mr-1"),
        value,
        variant=variant,
        cls="gap-1",
    )


def _start_lesson_button(uid: str, is_in_progress: bool, is_mastered: bool) -> Any:
    """Render the enrollment/start button based on learning state."""
    if is_mastered:
        return Badge("Mastered", variant=BadgeT.success, size=Size.sm)
    if is_in_progress:
        return Badge("In Progress", variant=BadgeT.secondary, size=Size.sm)
    return Button(
        "Start Lesson",
        variant=ButtonT.primary,
        size=Size.sm,
        hx_post=f"/api/lesson/{uid}/start",
        hx_swap="outerHTML",
        hx_target="this",
    )


class LessonUIComponents:
    """Centralized Lesson UI components."""

    @staticmethod
    def render_lesson_card(unit, compact=False) -> Any:
        """Individual Lesson card component using CardGenerator."""
        uid = unit.uid

        display_fields = (
            ["title", "domain", "tags"]
            if compact
            else ["title", "content", "domain", "tags", "complexity"]
        )

        action_buttons = Div(
            Button(
                "View",
                variant=ButtonT.outline,
                size=Size.sm,
                hx_get=f"/lesson/{uid}/details",
                hx_target="#modal" if compact else "#main-content",
            ),
            Button(
                "Edit",
                variant=ButtonT.ghost,
                size=Size.sm,
                hx_get=f"/lesson/{uid}/edit",
                hx_target="#modal",
            ),
            cls="flex gap-2",
        )

        return CardGenerator.from_dataclass(
            unit,
            display_fields=display_fields,
            actions=action_buttons,
            card_attrs={"id": f"lesson-{uid}", "cls": "border-l-4 border-blue-500 p-4"},
        )


# ============================================================================
# CLEAN UI ROUTES
# ============================================================================


def create_lesson_ui_routes(_app, rt, lesson_service):
    """
    Create Lesson UI routes.

    Args:
        lesson_service: LessonService (services.lesson).
    """

    logger.info("Lesson UI routes registered")

    @rt("/lesson/discovery")
    async def lesson_discovery_dashboard(_request) -> Any:
        """Discovery dashboard."""
        return Div(
            H1("Knowledge Discovery", cls="text-2xl font-bold mb-6"),
            Card(
                H3("Discovery Tools", cls="text-lg font-semibold mb-4"),
                Div(
                    Button("Find Connections", variant=ButtonT.primary, size=Size.sm, cls="mr-2"),
                    Button("Trending Topics", variant=ButtonT.secondary, size=Size.sm, cls="mr-2"),
                    Button("Knowledge Gaps", variant=ButtonT.outline, size=Size.sm),
                ),
                cls="p-6 mb-6",
            ),
            Card(
                H3("Recommended for You", cls="text-lg font-semibold mb-4"),
                P(
                    "Personalized knowledge recommendations will appear here",
                    cls="text-muted-foreground",
                ),
                cls="p-6 mb-6",
            ),
            Card(
                H3("Learning Paths", cls="text-lg font-semibold mb-4"),
                P("Suggested learning paths based on your interests", cls="text-muted-foreground"),
                cls="p-6",
            ),
            cls="container mx-auto p-6",
        )

    @rt("/lesson/analytics")
    async def lesson_analytics_dashboard(_request) -> Any:
        """Curriculum analytics dashboard."""
        return Div(
            H1("Lesson Analytics", cls="text-2xl font-bold mb-6"),
            Card(
                H3("Growth Metrics", cls="text-lg font-semibold mb-4"),
                P("Lesson growth and usage analytics", cls="text-muted-foreground"),
                cls="p-6 mb-6",
            ),
            Card(
                H3("Connection Analysis", cls="text-lg font-semibold mb-4"),
                P(
                    "Knowledge graph connectivity and relationship insights",
                    cls="text-muted-foreground",
                ),
                cls="p-6 mb-6",
            ),
            Card(
                H3("Domain Insights", cls="text-lg font-semibold mb-4"),
                P(
                    "Knowledge distribution and domain expertise mapping",
                    cls="text-muted-foreground",
                ),
                cls="p-6",
            ),
            cls="container mx-auto p-6",
        )

    @rt("/lesson/graph")
    async def lesson_graph_page(_request) -> Any:
        """Knowledge graph page."""
        return Card(
            H1("Knowledge Graph", cls="text-2xl font-bold mb-6"),
            P(
                "Interactive knowledge graph visualization will be implemented here",
                cls="text-muted-foreground",
            ),
            cls="p-6 container mx-auto",
        )

    @rt("/lesson/moc-nav")
    async def moc_nav_fragment(request) -> Any:
        """HTMX: Load Maps of Content navigation list for sidebar."""
        result = await lesson_service.list_root_organizers(limit=20)
        if result.is_error or not result.value:
            return P("No Maps of Content yet", cls="text-xs opacity-50 px-2")
        return Div(
            *[
                Anchor(
                    moc["title"],
                    href=f"/ku/{moc['uid']}",
                    cls="block text-xs hover:text-primary truncate px-2 py-0.5",
                )
                for moc in result.value
            ],
        )

    @rt("/lesson/{uid}/details")
    async def lesson_detail_page(request: Request, uid: str) -> Any:
        """Lesson detail page with full content rendering."""
        user_uid = require_authenticated_user(request)

        # Fetch lesson with content body
        result = await lesson_service.get_with_content(uid)
        if result.is_error:
            return await BasePage(
                content=Div(
                    Card(
                        CardBody(
                            H3("Lesson Not Found", cls="text-lg font-bold"),
                            P(
                                f"No lesson with identifier: {uid}",
                                cls="text-muted-foreground mt-2",
                            ),
                            ButtonLink(
                                "← Back to Lessons",
                                href="/lessons",
                                variant=ButtonT.ghost,
                                size=Size.sm,
                                cls="mt-4",
                            ),
                        ),
                    ),
                    cls="max-w-4xl mx-auto p-8",
                ),
                title="Lesson Not Found",
                request=request,
            )

        lesson, content_body = result.value
        # Fall back to lesson.content property when no :Content node exists
        if not content_body and getattr(lesson, "content", None):
            content_body = lesson.content

        # Record view
        await lesson_service.mastery.record_view(user_uid, uid)

        # Get learning state
        state_result = await lesson_service.mastery.get_learning_state(user_uid, uid)
        is_marked_read = state_result.value.is_marked_as_read if state_result.is_ok else False
        is_bookmarked = state_result.value.is_bookmarked if state_result.is_ok else False
        is_in_progress = (
            state_result.value.state.value == "in_progress" if state_result.is_ok else False
        )
        is_mastered = state_result.value.state.value == "mastered" if state_result.is_ok else False

        # Render markdown with TOC
        content_html, toc_html = render_markdown_with_toc(content_body or "")
        has_toc = bool(toc_html and toc_html.strip())

        # Breadcrumbs
        breadcrumb_path = [
            {"uid": "lessons", "title": "Lessons", "url": "/lessons"},
            {"uid": uid, "title": lesson.title, "url": ""},
        ]

        # Metadata badges
        metadata_items = []
        if lesson.domain:
            domain_label = getattr(lesson.domain, "value", str(lesson.domain))
            metadata_items.append(_metadata_badge("Domain:", domain_label, BadgeT.primary))
        if lesson.complexity:
            metadata_items.append(_metadata_badge("Complexity:", str(lesson.complexity.value)))
        if lesson.learning_level:
            metadata_items.append(_metadata_badge("Level:", str(lesson.learning_level.value)))
        if lesson.estimated_time_minutes:
            metadata_items.append(_metadata_badge("Time:", f"{lesson.estimated_time_minutes} min"))

        metadata_section = (
            Div(*metadata_items, cls="flex flex-wrap gap-2 mb-4") if metadata_items else Div()
        )

        # Learning objectives
        objectives_section = Div()
        if lesson.learning_objectives:
            objectives_section = Div(
                H3("Learning Objectives", cls="text-base font-semibold mb-2"),
                Ul(
                    *[
                        Li(obj, cls="text-sm text-muted-foreground")
                        for obj in lesson.learning_objectives
                    ],
                    cls="list-disc pl-5 space-y-1 mb-6",
                ),
            )

        # Tags
        tags_section = Div()
        if lesson.tags:
            tag_badges = [Badge(tag, variant=BadgeT.outline, size=Size.sm) for tag in lesson.tags]
            tags_section = Div(*tag_badges, cls="flex flex-wrap gap-1 mt-3")

        # Reading content
        reading_content = Div(
            NotStr(content_html or "No content available."),
            cls="prose prose-lg max-w-none",
        )

        # Action buttons
        mark_read_btn = Button(
            "Marked as Read" if is_marked_read else "Mark as Read",
            variant=ButtonT.success if is_marked_read else ButtonT.primary,
            size=Size.sm,
            hx_post=f"/api/lesson/{uid}/mark-read",
            hx_swap="outerHTML",
            hx_target="this",
            disabled=is_marked_read,
        )

        bookmark_btn = Button(
            "Bookmarked" if is_bookmarked else "Bookmark",
            variant=ButtonT.secondary if is_bookmarked else ButtonT.ghost,
            size=Size.sm,
            hx_post=f"/api/lesson/{uid}/bookmark",
            hx_swap="outerHTML",
            hx_target="this",
        )

        start_btn = _start_lesson_button(uid, is_in_progress, is_mastered)

        # Main content column
        main_column = Div(
            Breadcrumbs(path=breadcrumb_path, show_home=False),
            metadata_section,
            objectives_section,
            reading_content,
            # Actions below content
            Div(
                start_btn,
                mark_read_btn,
                bookmark_btn,
                cls="flex gap-2 border-t border-border pt-6 mt-8",
            ),
            # Metadata footer
            Div(tags_section, cls="border-t border-border pt-6 mt-8") if lesson.tags else Div(),
            cls="flex-1 min-w-0 max-w-4xl mx-auto px-6 lg:px-8 py-4 lg:py-6",
        )

        if has_toc:
            toc_sidebar = Div(
                Div(
                    H3("Contents", cls="font-semibold text-sm mb-3"),
                    Div(
                        NotStr(toc_html),
                        cls="prose prose-sm max-w-none toc-nav",
                    ),
                    cls="sticky top-20 p-5 max-h-[calc(100vh-6rem)] overflow-y-auto",
                ),
                cls="hidden lg:block w-56 shrink-0 border-r border-border",
            )
            content = Div(toc_sidebar, main_column, cls="flex")
        else:
            content = main_column

        return await BasePage(
            content=content,
            title=lesson.title,
            request=request,
            active_page="curriculum",
            page_type=PageType.CUSTOM,
        )

    @rt("/api/lesson/{uid}/start", methods=["POST"])
    async def start_lesson(request: Request, uid: str) -> Any:
        """Start a lesson (mark as in-progress). Returns updated button HTML for HTMX swap."""
        user_uid = require_authenticated_user(request)

        result = await lesson_service.mastery.mark_in_progress(user_uid, uid)

        if result.is_error:
            return Button(
                "Error",
                variant=ButtonT.error,
                size=Size.sm,
                disabled=True,
            )

        return Badge("In Progress", variant=BadgeT.secondary, size=Size.sm)

    @rt("/api/lesson/{uid}/mark-read", methods=["POST"])
    async def mark_lesson_as_read(request: Request, uid: str) -> Any:
        """Mark lesson as read. Returns updated button HTML for HTMX swap."""
        user_uid = require_authenticated_user(request)

        result = await lesson_service.mastery.mark_as_read(user_uid, uid)

        if result.is_error:
            return Button(
                "Error",
                variant=ButtonT.error,
                size=Size.sm,
                disabled=True,
            )

        return Button(
            "Marked as Read",
            variant=ButtonT.success,
            size=Size.sm,
            disabled=True,
        )

    @rt("/api/lesson/{uid}/bookmark", methods=["POST"])
    async def toggle_lesson_bookmark(request: Request, uid: str) -> Any:
        """Toggle lesson bookmark. Returns updated button HTML for HTMX swap."""
        user_uid = require_authenticated_user(request)

        result = await lesson_service.mastery.toggle_bookmark(user_uid, uid)

        if result.is_error:
            return Button(
                "Error",
                variant=ButtonT.error,
                size=Size.sm,
                disabled=True,
            )

        is_bookmarked = result.value

        return Button(
            "Bookmarked" if is_bookmarked else "Bookmark",
            variant=ButtonT.secondary if is_bookmarked else ButtonT.ghost,
            size=Size.sm,
            hx_post=f"/api/lesson/{uid}/bookmark",
            hx_swap="outerHTML",
            hx_target="this",
        )

    @rt("/lesson/{uid}/edit")
    async def lesson_edit_form(_request, uid: str) -> Any:
        """Edit lesson form fragment."""
        return Card(
            H2("Edit Lesson", cls="text-xl font-bold mb-4"),
            P(f"Edit form for lesson {uid} will be implemented here", cls="text-muted-foreground"),
            cls="p-6",
        )

    @rt("/lesson/{uid}/graph")
    async def lesson_graph_view(_request, uid: str) -> Any:
        """Lesson graph view centered on specific unit."""
        return Card(
            H2("Knowledge Graph", cls="text-xl font-bold mb-4"),
            P(
                f"Graph view centered on lesson {uid} will be implemented here",
                cls="text-muted-foreground",
            ),
            cls="p-6",
        )

    @rt("/static/js/knowledge.js")
    async def knowledge_javascript(_request) -> Any:
        """Serve knowledge-specific JavaScript."""
        js_content = """
        function closeModal() {
            document.getElementById('modal').innerHTML = '';
        }

        function refreshKnowledge() {
            htmx.trigger('#knowledge-container', 'refresh');
        }

        function expandKnowledgeCard(uid) {
            htmx.ajax('GET', `/lesson/${uid}/details`, '#knowledge-details');
        }

        document.addEventListener('htmx:afterSwap', function(evt) {
            if (evt.detail.target.id === 'knowledge-list') {
                console.log('Knowledge list updated');
            }
        });

        console.log('Knowledge UI JavaScript loaded');
        """

        return Response(js_content, media_type="application/javascript")

    return []  # Routes registered via @rt() decorators


__all__ = ["create_lesson_ui_routes"]
