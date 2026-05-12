"""
Explore PathStep Detail — Pure Rendering
==========================================

Renders the PathStep detail content fragment for /explore/ps/{uid}/content.
No async, no service calls — receives pre-fetched data.
"""

from typing import Any

from fasthtml.common import H3, Div, Li, NotStr, P, Ul

from adapters.inbound.path_steps_ui import _start_step_button, render_engagement_actions
from core.models.enums import UserRole
from core.models.type_hints import EntityUID
from core.services.ps_engagement.engagement import Engagement
from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.explore.ps_publish_state import render_publish_state, render_status_badge
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.breadcrumbs import Breadcrumbs
from ui.patterns.metadata_badge import metadata_badge
from ui.patterns.relationships import EntityRelationshipsSection
from ui.teaching.templates_panel import render_templates_panel_placeholder


def render_ps_not_found(uid: str) -> Div:
    """Render the not-found state for a PathStep detail page."""
    return Div(
        Card(
            CardBody(
                H3("Path Step Not Found", cls="text-lg font-bold"),
                P(
                    f"No path step with identifier: {uid}",
                    cls="text-muted-foreground mt-2",
                ),
                ButtonLink(
                    "\u2190 Back to Explore",
                    href="/explore",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    cls="mt-4",
                ),
            ),
        ),
        id="ps-detail-content",
        cls="max-w-4xl mx-auto p-8",
    )


def render_ps_detail_content(
    *,
    step: Any,
    uid: str,
    content_html: str,
    toc_html: str,
    is_marked_read: bool,
    is_bookmarked: bool,
    is_in_progress: bool,
    is_mastered: bool,
    user_uid: str | None,
    exercises: list[dict],
    engagement: Engagement | None,
    user_role: UserRole | None = None,
) -> Div:
    """Render the full PathStep detail content fragment.

    Args:
        step: The PathStep entity.
        uid: PathStep UID.
        content_html: Pre-rendered markdown HTML.
        toc_html: Pre-rendered table-of-contents HTML.
        is_marked_read: Whether the user marked this step as read.
        is_bookmarked: Whether the user bookmarked this step.
        is_in_progress: Whether the user is currently working on this step.
        is_mastered: Whether the user has mastered this step.
        user_uid: Current user UID, or None if unauthenticated.
        exercises: Exercise dicts (used for unauthenticated exercise list).
        engagement: Active engagement (state="engaged") for this user+PS, or
            None if no active engagement. Drives the Engage/Abandon button
            group rendered above the learning-state action row.
        user_role: Viewer's role, or None for unauthenticated. Used to gate
            the Publish button (TEACHER+ only) in the action area.
    """
    is_teacher = user_role is not None and user_role.has_permission(UserRole.TEACHER)
    has_toc = bool(toc_html and toc_html.strip())

    # Breadcrumbs
    breadcrumb_path = [
        {"uid": "explore", "title": "Explore", "url": "/explore"},
        {"uid": uid, "title": step.title, "url": ""},
    ]

    # Metadata badges
    metadata_items = [render_status_badge(getattr(step, "status", None))]
    if step.domain:
        domain_label = getattr(step.domain, "value", str(step.domain))
        metadata_items.append(metadata_badge("Domain:", domain_label, BadgeT.primary))
    if step.complexity:
        metadata_items.append(metadata_badge("Complexity:", str(step.complexity.value)))
    if step.learning_level:
        metadata_items.append(metadata_badge("Level:", str(step.learning_level.value)))
    if step.estimated_time_minutes:
        metadata_items.append(metadata_badge("Time:", f"{step.estimated_time_minutes} min"))
    if step.estimated_hours:
        metadata_items.append(metadata_badge("Hours:", f"{step.estimated_hours:.1f}h"))

    metadata_section = Div(*metadata_items, cls="flex flex-wrap gap-2 mb-4")

    # Learning objectives
    objectives_section = Div()
    if step.learning_objectives:
        objectives_section = Div(
            H3("Learning Objectives", cls="text-base font-semibold mb-2"),
            Ul(
                *[Li(obj, cls="text-sm text-muted-foreground") for obj in step.learning_objectives],
                cls="list-disc pl-5 space-y-1 mb-6",
            ),
        )

    # Tags
    tags_section = Div()
    if step.tags:
        tag_badges = [Badge(tag, variant=BadgeT.outline, size=Size.sm) for tag in step.tags]
        tags_section = Div(*tag_badges, cls="flex flex-wrap gap-1 mt-3")

    # Reading content
    reading_content = Div(
        NotStr(content_html or "No content available."),
        cls="prose prose-lg max-w-none",
    )

    # Exercises stay visible with an empty state (the workflow entry point).
    # Submissions + Feedback collapse to an empty Div when the user has no
    # activity yet — see render_ps_submissions_and_feedback.
    submissions_section: Any = Div()
    feedback_section: Any = Div()
    if user_uid:
        exercises_section: Any = Div(
            H3("Exercises", cls="text-base font-semibold mb-2 mt-8"),
            Div(
                id=f"ps-exercises-{uid}",
                hx_get=f"/learning-loop/ps/{uid}/exercises",
                hx_trigger="load",
                hx_swap="innerHTML",
            ),
            cls="border-t border-border pt-6 mt-8",
        )
        submissions_section = Div(
            id=f"ps-submissions-feedback-{uid}",
            hx_get=f"/learning-loop/ps/{uid}/submissions-and-feedback",
            hx_trigger="load",
            hx_swap="innerHTML",
        )
        feedback_section = Div()
    else:
        exercises_section = _render_unauthenticated_exercises(uid, exercises)

    # Action buttons
    if user_uid:
        mark_read_btn = Button(
            "Marked as Read" if is_marked_read else "Mark as Read",
            variant=ButtonT.success if is_marked_read else ButtonT.primary,
            size=Size.sm,
            hx_post=f"/api/path-steps/{uid}/mark-read",
            hx_swap="outerHTML",
            hx_target="this",
            disabled=is_marked_read,
        )
        bookmark_btn = Button(
            "Bookmarked" if is_bookmarked else "Bookmark",
            variant=ButtonT.secondary if is_bookmarked else ButtonT.ghost,
            size=Size.sm,
            hx_post=f"/api/path-steps/{uid}/bookmark",
            hx_swap="outerHTML",
            hx_target="this",
        )
        action_area: Any = Div(
            render_engagement_actions(uid, engagement),
            render_publish_state(uid, getattr(step, "status", None), is_teacher),
            Div(
                _start_step_button(uid, is_in_progress, is_mastered),
                mark_read_btn,
                bookmark_btn,
                cls="flex gap-2",
            ),
            cls="flex flex-col gap-3 border-t border-border pt-6 mt-8",
        )
    else:
        action_area = Div(
            ButtonLink(
                "Log in to track your progress",
                href="/login",
                variant=ButtonT.ghost,
                size=Size.sm,
            ),
            cls="border-t border-border pt-6 mt-8",
        )

    # Teacher-only: Activity Templates panel. HTMX-loaded so detach + create
    # flows can refresh in place without re-rendering the entire PS detail.
    templates_panel: Any = (
        render_templates_panel_placeholder(uid) if is_teacher else Div()
    )

    # Main content column
    main_column = Div(
        Breadcrumbs(path=breadcrumb_path, show_home=False),
        metadata_section,
        objectives_section,
        reading_content,
        exercises_section,
        submissions_section,
        feedback_section,
        action_area,
        templates_panel,
        Div(tags_section, cls="border-t border-border pt-6 mt-8") if step.tags else Div(),
        EntityRelationshipsSection(entity_uid=EntityUID(uid), entity_type="ps"),
        cls="flex-1 min-w-0 max-w-4xl",
    )

    if has_toc:
        toc_sidebar = Div(
            Div(
                H3("Contents", cls="font-semibold text-sm mb-3"),
                Div(NotStr(toc_html), cls="prose prose-sm max-w-none toc-nav"),
                cls="sticky top-20 p-5 max-h-[calc(100vh-6rem)] overflow-y-auto",
            ),
            cls="hidden lg:block w-56 shrink-0 border-l border-border",
        )
        return Div(main_column, toc_sidebar, cls="flex gap-6")
    return main_column


def _render_unauthenticated_exercises(uid: str, exercises: list[dict]) -> Div:
    """Render read-only exercise links for unauthenticated users."""
    if not exercises:
        return Div()

    exercise_links = []
    for ex in exercises:
        ex_uid = ex.get("uid", "")
        ex_title = ex.get("title") or ex_uid
        ex_time = ex.get("estimated_time_minutes")
        time_note = f" \u00b7 {ex_time} min" if ex_time else ""
        exercise_links.append(
            Li(
                ButtonLink(
                    f"{ex_title}{time_note} \u2192",
                    href=f"/exercises/get?uid={ex_uid}&from_ps={uid}",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                ),
                cls="list-none",
            )
        )
    return Div(
        H3("Exercises", cls="text-base font-semibold mb-2 mt-8"),
        Ul(*exercise_links, cls="list-none p-0 space-y-1"),
        cls="border-t border-border pt-6 mt-8",
    )
