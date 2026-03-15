"""
Lesson UI Routes — Lesson-Specific UI Endpoints
================================================

Lesson detail views, creation forms, and fragment endpoints.
The /ku route has moved to ku_ui.py (served by KuService).
"""

from typing import Any

from fasthtml.common import H1, H2, H3, Div, P
from fasthtml.common import A as Anchor
from starlette.responses import Response

from core.models.lesson.lesson_request import LessonCreateRequest
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.layout import Size
from ui.patterns.card_generator import CardGenerator
from ui.patterns.form_generator import FormGenerator

logger = get_logger("skuel.routes.lesson.ui")


# ============================================================================
# UI COMPONENT LIBRARY - Reusable Lesson components
# ============================================================================


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

        card = CardGenerator.from_dataclass(
            unit,
            display_fields=display_fields,
            field_renderers={},
            card_attrs={"id": f"lesson-{uid}", "cls": "border-l-4 border-blue-500 p-4"},
        )

        buttons = [
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
        ]

        return Card(Div(card, Div(*buttons, cls="flex gap-2 mt-3"), cls="p-4"))

    @staticmethod
    def render_create_lesson_form() -> Any:
        """Create Lesson form using FormGenerator."""
        return Card(
            H2("Create Lesson", cls="text-xl font-bold mb-4"),
            FormGenerator.from_model(
                LessonCreateRequest,
                action="/api/lesson",
                method="POST",
                include_fields=[
                    "title",
                    "content",
                    "domain",
                    "tags",
                    "prerequisites",
                    "complexity",
                    "confidence",
                ],
                form_attrs={
                    "hx_post": "/api/lesson",
                    "hx_target": "#lesson-container",
                    "hx_swap": "outerHTML",
                },
                submit_label="Create Lesson",
            ),
            cls="p-6 max-w-2xl mx-auto",
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

    @rt("/lesson/create")
    async def lesson_create_form(_request) -> Any:
        """Create lesson form."""
        return LessonUIComponents.render_create_lesson_form()

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
                    href=f"/lesson/{moc['uid']}",
                    cls="block text-xs hover:text-primary truncate px-2 py-0.5",
                )
                for moc in result.value
            ],
        )

    @rt("/lesson/{uid}/details")
    async def lesson_details_modal(_request, uid: str) -> Any:
        """Lesson details modal fragment."""
        return Card(
            H2("Lesson Details", cls="text-xl font-bold mb-4"),
            P(
                f"Detailed view for lesson {uid} will be implemented here",
                cls="text-muted-foreground",
            ),
            cls="p-6",
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
