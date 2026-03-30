"""
KU Reading UI Routes - Phase A
===============================

User-facing routes for reading Knowledge Units with:
- Markdown content rendering with table of contents
- Breadcrumbs from MOC context
- Mark as read / bookmark actions
- Next/prev navigation via MOC ORGANIZES order
- KU metadata display (domain, complexity, tags)
- Exercises practicing this knowledge (Ku -> Exercise loop entry point)
- Lateral relationships visualization

Routes:
- GET /ku/{uid} - KU detail page with reading interface
"""

import contextlib
import json
from typing import Any

from fasthtml.common import H3, Div, NotStr, P, Request, Span

from adapters.inbound.auth import require_authenticated_user
from core.models.enums.submissions_enums import ExerciseScope
from core.utils.logging import get_logger
from core.utils.markdown_renderer import render_markdown_with_toc
from ui.buttons import ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.exercises.inline_form import render_inline_exercise_form
from ui.feedback import Badge, BadgeT
from ui.forms.inline_form_template import render_inline_form_template
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.breadcrumbs import Breadcrumbs
from ui.patterns.relationships import EntityRelationshipsSection

logger = get_logger("skuel.routes.ku.reading.ui")


def _metadata_badge(label: str, value: str, variant: BadgeT = BadgeT.ghost) -> Any:
    """Render a metadata badge."""
    return Badge(
        Span(label, cls="font-medium mr-1"),
        value,
        variant=variant,
        cls="gap-1",
    )


def _parse_form_schema(raw: Any) -> list[dict] | None:
    """Parse form_schema from Neo4j (may be JSON string, list, or None)."""
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) and parsed else None
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(raw, list) and raw:
        return raw
    return None


def _exercises_for_ku_section(exercises: list[dict]) -> Any:
    """Exercises that practice this knowledge — Ku -> Exercise loop entry point.

    Exercises with form_schema render as inline forms. Others show as links.
    """
    if not exercises:
        return Div()

    rows = []
    for e in exercises:
        form_schema = _parse_form_schema(e.get("form_schema"))

        if form_schema:
            # Inline form — embedded directly in the lesson
            rows.append(
                render_inline_exercise_form(
                    exercise_uid=e.get("uid", ""),
                    form_schema=form_schema,
                    exercise_title=e.get("title"),
                )
            )
        else:
            # Standard exercise link
            scope = e.get("scope", "personal")
            scope_variant = BadgeT.secondary if scope == ExerciseScope.ASSIGNED else BadgeT.ghost
            due = e.get("due_date")
            due_span = Span(f" · due {due}", cls="text-xs text-muted-foreground") if due else None
            row_parts: list[Any] = [
                Span(e.get("title", "Untitled Exercise"), cls="text-sm font-medium"),
                Badge(scope.title(), variant=scope_variant, size=Size.sm, cls="ml-2"),
            ]
            if due_span:
                row_parts.append(due_span)
            rows.append(Div(*row_parts, cls="flex items-center py-1.5"))

    return Div(
        H3("Practice This Knowledge", cls="text-base font-semibold mb-3"),
        P(
            "These exercises develop understanding of this knowledge unit.",
            cls="text-sm text-muted-foreground mb-3",
        ),
        Div(*rows, cls="space-y-2"),
        cls="border-t border-border pt-6 mt-8",
    )


def _form_templates_section(form_templates: list[dict]) -> Any:
    """Render embedded FormTemplates as inline forms."""
    if not form_templates:
        return Div()

    rows = []
    for ft in form_templates:
        form_schema = _parse_form_schema(ft.get("form_schema"))
        if form_schema:
            rows.append(
                render_inline_form_template(
                    form_template_uid=ft.get("uid", ""),
                    form_schema=form_schema,
                    title=ft.get("title"),
                    instructions=ft.get("instructions"),
                )
            )

    if not rows:
        return Div()

    return Div(
        H3("Forms", cls="text-base font-semibold mb-3"),
        Div(*rows, cls="space-y-4"),
        cls="border-t border-border pt-6 mt-8",
    )


async def _render_ku_detail(
    request: Request,
    ku: Any,
    content_body: str,
    uid: str,
    user_uid: str,
    ku_interaction_service: Any,
    exercises_service: Any,
    form_template_service: Any,
) -> Any:
    """Render a detail page for an atomic Ku entity.

    Atomic Kus are lightweight reference nodes — simpler layout than Lessons.
    Content comes from the description field, not a :Content child node.
    """
    # Record view (best-effort — mastery service is Lesson-backed)
    with contextlib.suppress(Exception):  # safety-net: mastery service may not support Ku labels
        await ku_interaction_service.record_view(user_uid, uid)

    # Render content
    content_html, toc_html = render_markdown_with_toc(content_body)
    has_toc = bool(toc_html and toc_html.strip())

    # Metadata badges
    metadata_items = []
    if getattr(ku, "domain", None):
        domain_label = getattr(ku.domain, "value", str(ku.domain))
        metadata_items.append(_metadata_badge("Domain:", domain_label, BadgeT.primary))
    if getattr(ku, "namespace", None):
        metadata_items.append(_metadata_badge("Namespace:", ku.namespace))
    if getattr(ku, "ku_category", None):
        metadata_items.append(_metadata_badge("Category:", ku.ku_category))

    metadata_section = (
        Div(*metadata_items, cls="flex flex-wrap gap-2") if metadata_items else None
    )

    # Tags
    tags_section = None
    if getattr(ku, "tags", None):
        tag_badges = [Badge(tag, variant=BadgeT.outline, size=Size.sm) for tag in ku.tags]
        tags_section = Div(*tag_badges, cls="flex flex-wrap gap-1 mt-3")

    # Exercises
    exercises_for_ku: list[dict] = []
    if exercises_service:
        exercises_result = await exercises_service.get_exercises_for_curriculum(uid)
        exercises_for_ku = exercises_result.value if exercises_result.is_ok else []

    # FormTemplates
    form_templates: list[dict] = []
    if form_template_service:
        ft_result = await form_template_service.get_for_lesson(uid)
        form_templates = ft_result.value if ft_result.is_ok else []

    # Breadcrumbs
    breadcrumb_path = [
        {"uid": "knowledge", "title": "Knowledge", "url": "/ku"},
        {"uid": uid, "title": ku.title, "url": ""},
    ]

    reading_content = Div(
        NotStr(content_html or "No content available."),
        cls="prose prose-lg max-w-none",
    )

    # Metadata footer
    metadata_footer_items = []
    if metadata_section:
        metadata_footer_items.append(metadata_section)
    if tags_section:
        metadata_footer_items.append(tags_section)

    metadata_footer = (
        Div(*metadata_footer_items, cls="border-t border-border pt-6 mt-8")
        if metadata_footer_items
        else Div()
    )

    main_column = Div(
        Breadcrumbs(path=breadcrumb_path, show_home=False),
        reading_content,
        metadata_footer,
        _exercises_for_ku_section(exercises_for_ku),
        _form_templates_section(form_templates),
        Div(
            EntityRelationshipsSection(entity_uid=uid, entity_type="ku"),
            cls="mt-8",
        ),
        cls="flex-1 min-w-0 max-w-4xl mx-auto px-6 lg:px-8 py-4 lg:py-6",
    )

    if has_toc:
        toc_sidebar = Div(
            Div(
                H3("Contents", cls="font-semibold text-sm mb-3"),
                Div(NotStr(toc_html), cls="prose prose-sm max-w-none toc-nav"),
                cls="sticky top-20 p-5 max-h-[calc(100vh-6rem)] overflow-y-auto",
            ),
            cls="hidden lg:block w-56 shrink-0 border-r border-border",
        )
        content = Div(toc_sidebar, main_column, cls="flex")
    else:
        content = main_column

    return await BasePage(
        content=content,
        title=ku.title,
        request=request,
        active_page="knowledge",
        page_type=PageType.CUSTOM,
    )


def create_ku_reading_ui_routes(
    app: Any,
    rt: Any,
    ku_service: Any,
    ku_interaction_service: Any,
    exercises_service: Any,
    form_template_service: Any = None,
    **_kwargs: Any,
) -> list[Any]:
    """
    Create KU reading UI routes.

    Args:
        app: FastHTML app instance
        rt: FastHTML route decorator
        ku_service: KuService facade (for atomic Ku entities)
        ku_interaction_service: Interaction tracking service
        exercises_service: Exercise service (for REQUIRES_KNOWLEDGE reverse lookup)
        form_template_service: FormTemplate service (for EMBEDS_FORM reverse lookup)

    Returns:
        List of registered route functions
    """

    @rt("/ku/{uid}")
    async def ku_detail_page(request: Request, uid: str) -> Any:
        """KU detail page — renders atomic Ku entities from KuService."""
        user_uid = require_authenticated_user(request)

        # Fetch atomic Ku
        ku_result = await ku_service.get_ku(uid) if ku_service else None

        if not ku_result or ku_result.is_error or not ku_result.value:
            return await BasePage(
                content=Div(
                    Card(
                        CardBody(
                            H3("Knowledge Unit Not Found", cls="text-lg font-bold"),
                            P(f"No KU with identifier: {uid}", cls="text-muted-foreground mt-2"),
                            ButtonLink(
                                "← Back to Knowledge",
                                href="/ku",
                                variant=ButtonT.ghost,
                                size=Size.sm,
                                cls="mt-4",
                            ),
                        ),
                    ),
                    cls="max-w-4xl mx-auto p-8",
                ),
                title="KU Not Found",
                request=request,
            )

        ku = ku_result.value
        content_body = ku.description or ""

        return await _render_ku_detail(
            request, ku, content_body, uid, user_uid,
            ku_interaction_service, exercises_service, form_template_service,
        )

    logger.info("KU reading UI routes registered: /ku/{uid}")

    return [
        ku_detail_page,
    ]


__all__ = ["create_ku_reading_ui_routes"]
