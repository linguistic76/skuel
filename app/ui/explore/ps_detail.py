"""
Explore PathStep Detail — Reading-First Design
===============================================

Reading-column layout for /explore/ps/{uid}/content.
Matches the KU reader design language: calm centered column,
real reading typography, hero card with progress tracking.

Design reference: data/design_handoff_pathstep/pathstep.html

No async, no service calls — receives pre-fetched data.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H1,
    H2,
    A,
    Button,
    Div,
    Li,
    NotStr,
    P,
    Section,
    Span,
    Template,
    Ul,
)

from core.models.enums import UserRole
from ui.components import Icon
from ui.library.resource_chip import resource_chip
from ui.patterns.detail_nav import (
    detail_back_link,
    detail_footer_nav,
    render_entity_not_found,
)
from ui.primitives import section_label
from ui.teaching.templates_panel import render_templates_panel_placeholder

if TYPE_CHECKING:
    from fasthtml.common import FT

    from ui.page_contexts import NextStepRelatedGroup, RelatedConceptChip

_COLUMN_CLS = "mx-auto max-w-[760px] px-5 pt-8 pb-20"


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def render_ps_not_found(uid: str) -> Div:
    """Render the not-found state for a PathStep detail fragment."""
    return render_entity_not_found(
        entity_label="Path step",
        uid=uid,
        back_href="/explore",
        back_label="Explore",
        column_cls=_COLUMN_CLS,
        content_id="ps-detail-content",
    )


def render_ps_detail_content(
    *,
    step: Any,
    uid: str,
    content_html: str,
    is_marked_read: bool,
    is_bookmarked: bool,
    is_in_progress: bool,
    is_mastered: bool,
    user_uid: str | None,
    user_role: UserRole | None = None,
    has_task_templates: bool = False,
    kus: list[dict] | None = None,
    resources: list[dict] | None = None,
    show_related: bool = False,
    show_next_step_related: bool = False,
    # Retained for API compatibility; not rendered in this design iteration.
    toc_html: str = "",
    exercises: list[dict] | None = None,
    engagement: Any = None,
) -> Div:
    """Reading-first PathStep detail content fragment.

    Serves as the HTMX fragment for GET /explore/ps/{uid}/content.
    The Alpine component (pathstep) is registered in ps-detail.js,
    loaded in the shell before the fragment arrives.

    Args:
        step: PathStep entity.
        uid: PathStep UID.
        content_html: Pre-rendered markdown HTML (skuel-prose body).
        is_marked_read: Whether the user marked this step as read.
        is_bookmarked: Whether the user bookmarked this step.
        is_in_progress: Whether the user is currently working on this step.
        is_mastered: Whether the user has mastered this step.
        user_uid: Current user UID, or None if unauthenticated.
        user_role: Viewer's role — TEACHER+ gets the read-only Activity
            Templates panel (HTMX fragment from the teaching route).
        has_task_templates: True when the PS has TaskTemplates — "Start learning"
            triggers engagement (task spawn) rather than read-progress toggle.
        kus: Atomic Kus this step composes (USES_KU) — rendered as reader links.
        resources: Curated Resources this step cites (CITES_RESOURCE) —
            rendered as reference chips (author/year, source link when known).
        show_related: Mount the lazy "Related concepts" fragment (PS→PS vector
            similarity). FULL tier only — False (section absent) when the
            vector search service is unavailable.
        show_next_step_related: Mount the lazy "Related to your next step"
            fragment (ZPD next-step Kus + their vector neighbours). FULL tier
            + authenticated only — False (section absent) when ZPD or vector
            search is unavailable or the viewer is anonymous.
        toc_html: Not used in this layout (no TOC sidebar).
        exercises: Not rendered inline in this design (deferred).
        engagement: Not rendered inline in this design (deferred).
    """
    progress_state = (
        "read"
        if (is_marked_read or is_mastered)
        else "learning"
        if is_in_progress
        else "not_started"
    )

    seed = {
        "uid": uid,
        "progress_state": progress_state,
        "is_bookmarked": is_bookmarked,
        "has_task_templates": has_task_templates,
        "blocking": [],  # populated via orchestrator in a future iteration
        "prev_step": None,
        "next_step": None,
    }
    # Seed goes INLINE in the x-data expression, never via a window global set
    # by a sibling <script>: htmx defers inline-script evaluation to the settle
    # phase, but Alpine's MutationObserver initializes the swapped tree first —
    # a global would still be undefined at init (uid='' broke Start learning).
    seed_json = json.dumps(seed, default=str)

    return Div(
        detail_back_link("Explore", "/explore"),
        _hero_card(step, uid, user_uid),
        _body_section(content_html) if content_html else Div(),
        _kus_section(kus) if kus else Div(),
        _resources_section(resources) if resources else Div(),
        _related_placeholder(uid) if show_related else Div(),
        _next_step_related_placeholder() if show_next_step_related else Div(),
        _tasks_section(uid) if user_uid else Div(),
        _learning_loop_section(uid) if user_uid else Div(),
        render_templates_panel_placeholder(uid)
        if user_role is not None and user_role.has_permission(UserRole.TEACHER)
        else Div(),
        _deps_accordion(),
        detail_footer_nav("Back to Explore", "/explore"),
        id="ps-detail-content",
        cls=_COLUMN_CLS,
        **{"x-data": f"pathstep({seed_json})"},
    )


# ---------------------------------------------------------------------------
# Hero card
# ---------------------------------------------------------------------------


def _hero_card(step: Any, uid: str, user_uid: str | None) -> "FT":
    title = getattr(step, "title", uid) or uid
    description = getattr(step, "description", "") or getattr(step, "intent", "") or ""
    est_minutes = getattr(step, "estimated_time_minutes", None)
    tags = getattr(step, "tags", ()) or ()

    return Section(
        # Accent rail
        Div(cls="h-1 bg-strength-core"),
        # Card body
        Div(
            # Kind badge row + bookmark
            Div(
                _kind_badge(),
                _bookmark_btn(uid) if user_uid else Div(),
                cls="flex items-center justify-between gap-3 mb-[18px]",
            ),
            # Title
            H1(
                title,
                id="ps-title",
                cls="text-3xl font-extrabold leading-[1.12] tracking-[-0.02em]",
            ),
            # Description/central idea
            P(
                description,
                cls="mt-[13px] text-base leading-[1.55] text-foreground/75 max-w-[62ch]",
            )
            if description
            else Div(),
            # Meta chips
            _meta_chips(est_minutes, tags),
            cls="px-8 pt-[30px] pb-[26px]",
        ),
        # Action bar (authenticated users only)
        _action_bar(uid) if user_uid else _unauthenticated_cta(),
        cls="bg-card border border-border rounded-[12px] shadow-[0_1px_3px_rgba(0,0,0,0.04)] overflow-hidden",
        role="region",
        **{"aria-labelledby": "ps-title"},
    )


def _kind_badge() -> "FT":
    return Span(
        Icon("route", cls="w-[13px] h-[13px]"),
        " Path step",
        cls=(
            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-[6px] "
            "bg-blue-50 text-blue-600 "
            "text-xs font-semibold whitespace-nowrap"
        ),
    )


def _bookmark_btn(uid: str) -> "FT":
    return Button(
        Icon("bookmark", cls="w-3.5 h-3.5"),
        Span("", **{"x-text": "bookmarked ? 'Saved' : 'Save'"}),
        type="button",
        cls=(
            "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md "
            "text-xs font-semibold border transition-colors "
            "focus:outline-hidden focus:shadow-focus"
        ),
        **{
            "@click": "toggleBookmark()",
            ":aria-pressed": "bookmarked.toString()",
            ":aria-label": "bookmarked ? 'Remove bookmark' : 'Bookmark this step'",
            ":class": (
                "bookmarked "
                "? 'border-strength-core text-strength-core bg-strength-core/5' "
                ": 'border-border text-muted-foreground bg-card hover:bg-muted hover:text-foreground'"
            ),
        },
    )


def _meta_chips(est_minutes: int | None, tags: tuple | list) -> "FT":
    items: list[Any] = []

    if est_minutes:
        items.append(
            Span(
                Icon("clock", cls="w-3.5 h-3.5"),
                f" {est_minutes} min",
                cls="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground",
            )
        )

    tag_list = list(tags)[:6]
    if tag_list:
        if items:
            items.append(Span(cls="w-px h-3.5 bg-border"))
        for tag in tag_list:
            items.append(
                Span(
                    Span(cls="w-1.5 h-1.5 rounded-full bg-strength-core"),
                    f" {tag}",
                    cls="inline-flex items-center gap-1.5 text-xs font-semibold text-foreground/85",
                )
            )

    if not items:
        return Div()
    return Div(*items, cls="flex items-center gap-3.5 flex-wrap mt-[18px]")


# ---------------------------------------------------------------------------
# Action bar
# ---------------------------------------------------------------------------


def _action_bar(uid: str) -> "FT":
    return Div(
        # Progress bar
        Div(
            Div(
                cls="h-full rounded-full bg-strength-core transition-[width] duration-350 ease-out",
                **{":style": "'width:' + progressPct + '%'"},
            ),
            cls="h-[5px] rounded-full bg-border overflow-hidden mb-3.5",
            role="progressbar",
            aria_valuemin="0",
            aria_valuemax="100",
            **{":aria-valuenow": "progressPct"},
        ),
        # Status + primary action
        Div(
            # Status indicator (left)
            Div(
                # not_started
                Span(
                    Span(cls="w-2 h-2 rounded-full bg-muted-foreground/50"),
                    " Not started",
                    cls="inline-flex items-center gap-1.5 text-13 font-semibold text-muted-foreground whitespace-nowrap",
                    **{"x-show": "status === 'not_started'"},
                ),
                # learning
                Span(
                    Span(cls="w-2 h-2 rounded-full bg-warning"),
                    " Learning",
                    cls="inline-flex items-center gap-1.5 text-13 font-semibold text-warning whitespace-nowrap",
                    **{"x-show": "status === 'learning'"},
                ),
                # read / completed
                Span(
                    Icon("check", cls="w-[15px] h-[15px]"),
                    " Completed",
                    cls="inline-flex items-center gap-1.5 text-13 font-semibold text-priority-low whitespace-nowrap",
                    **{"x-show": "status === 'read'"},
                ),
                cls="flex items-center gap-2",
            ),
            # Primary action (right)
            Div(
                # Start learning / Mark as read
                Button(
                    Span(
                        "",
                        **{"x-text": "status === 'learning' ? 'Mark as read' : 'Start learning'"},
                    ),
                    Icon("arrow-right", cls="w-[15px] h-[15px]"),
                    type="button",
                    cls=(
                        "inline-flex items-center gap-2 px-[18px] py-[9px] rounded-lg "
                        "bg-primary text-primary-foreground "
                        "text-13 font-semibold hover:opacity-90 "
                        "focus:outline-hidden focus:shadow-focus whitespace-nowrap"
                    ),
                    **{
                        "x-show": "status !== 'read'",
                        "@click": "advance()",
                    },
                ),
                # Review again (read state)
                Button(
                    Icon("rotate-ccw", cls="w-3.5 h-3.5"),
                    " Review again",
                    type="button",
                    cls=(
                        "inline-flex items-center gap-1.5 px-4 py-[9px] rounded-lg "
                        "border border-border bg-card "
                        "text-13 font-semibold text-foreground/80 "
                        "hover:bg-muted focus:outline-hidden focus:shadow-focus"
                    ),
                    **{
                        "x-show": "status === 'read'",
                        "@click": "reviewAgain()",
                    },
                ),
                cls="flex items-center gap-2.5",
            ),
            cls="flex items-center justify-between gap-3.5 flex-wrap",
        ),
        cls="border-t border-border bg-muted/40 px-8 py-4",
    )


def _unauthenticated_cta() -> "FT":
    return Div(
        A(
            "Log in to track your progress",
            Icon("arrow-right", cls="w-[15px] h-[15px]"),
            href="/login",
            cls=(
                "inline-flex items-center gap-2 px-[18px] py-[9px] rounded-lg "
                "bg-primary text-primary-foreground "
                "text-13 font-semibold hover:opacity-90"
            ),
        ),
        cls="border-t border-border bg-muted/40 px-8 py-4 flex justify-end",
    )


# ---------------------------------------------------------------------------
# Body content
# ---------------------------------------------------------------------------


def _body_section(content_html: str) -> "FT":
    return Section(
        section_label("The idea", tag=H2, id="idea-h"),
        Div(NotStr(content_html), cls="skuel-prose"),
        cls="mt-[30px]",
        role="region",
        **{"aria-labelledby": "idea-h"},
    )


# ---------------------------------------------------------------------------
# Knowledge units section
# ---------------------------------------------------------------------------


def _kus_section(kus: list[dict]) -> "FT":
    """Atomic Kus this PathStep composes (USES_KU edges) as reader links."""
    return Section(
        section_label("Knowledge in this step", tag=H2, id="ps-kus-h"),
        Div(
            *[
                A(
                    ku.get("title") or ku["uid"],
                    href=f"/explore/ku/{ku['uid']}",
                    cls=(
                        "inline-flex items-center px-3 py-1.5 rounded-full border "
                        "border-border bg-muted/40 text-13 font-medium "
                        "text-foreground hover:bg-accent hover:text-accent-foreground"
                    ),
                )
                for ku in kus
                if ku.get("uid")
            ],
            cls="flex flex-wrap gap-2",
        ),
        cls="mt-[24px]",
        role="region",
        **{"aria-labelledby": "ps-kus-h"},
    )


# ---------------------------------------------------------------------------
# Resources section
# ---------------------------------------------------------------------------


def _resources_section(resources: list[dict]) -> "FT":
    """Curated Resources this PathStep cites (CITES_RESOURCE edges).

    Each chip links to the in-app Resource detail page (the citation click
    destination); the external source link lives there. See ui/library/resource_chip.
    """
    return Section(
        section_label("Resources", tag=H2, id="ps-resources-h"),
        Div(
            *[resource_chip(r) for r in resources if r.get("uid")],
            cls="flex flex-wrap gap-2",
        ),
        cls="mt-[24px]",
        role="region",
        **{"aria-labelledby": "ps-resources-h"},
    )


# ---------------------------------------------------------------------------
# Related concepts section (vector similarity — read-time lens)
# ---------------------------------------------------------------------------


def _related_placeholder(uid: str) -> "FT":
    """Lazy HTMX mount for the Related-concepts section.

    The fragment returns the full section (heading included) or an empty div,
    so an empty/failed lookup leaves no orphaned heading behind.
    """
    return Div(
        id="ps-related-fragment",
        **{
            "hx-get": f"/explore/ps/{uid}/related",
            "hx-trigger": "load",
            "hx-swap": "outerHTML",
        },
    )


def render_ps_related_concepts(related: "list[RelatedConceptChip]") -> "FT":
    """Related concepts — vector-similar PathSteps as reader chips.

    Read-time lens over embeddings: no edges exist or are created for these
    neighbours. Ordered by similarity (scores not shown); each chip links to
    the neighbour's detail page. Empty input collapses to an empty div so
    the section vanishes entirely rather than rendering a bare heading.
    """
    items = [r for r in related if r.get("uid")]
    if not items:
        return Div(id="ps-related-fragment")
    return Section(
        section_label("Related concepts", tag=H2, id="ps-related-h"),
        Div(
            *[
                A(
                    r.get("title") or r["uid"],
                    href=f"/explore/ps/{r['uid']}",
                    cls=(
                        "inline-flex items-center px-3 py-1.5 rounded-full border "
                        "border-border bg-muted/40 text-13 font-medium "
                        "text-foreground hover:bg-accent hover:text-accent-foreground"
                    ),
                )
                for r in items
            ],
            cls="flex flex-wrap gap-2",
        ),
        id="ps-related-fragment",
        cls="mt-[24px]",
        role="region",
        **{"aria-labelledby": "ps-related-h"},
    )


# ---------------------------------------------------------------------------
# "Related to your next step" section (ZPD proximal zone + vector similarity)
# ---------------------------------------------------------------------------


def _next_step_related_placeholder() -> "FT":
    """Lazy HTMX mount for the "Related to your next step" section.

    The fragment is user-scoped (ZPD proximal zone), not PS-scoped, so the
    endpoint carries no uid. Returns the full section or an empty div, so an
    empty/failed lookup leaves no orphaned heading behind.
    """
    return Div(
        id="ps-next-step-fragment",
        **{
            "hx-get": "/explore/next-step/related",
            "hx-trigger": "load",
            "hx-swap": "outerHTML",
        },
    )


def render_ps_next_step_related(groups: "list[NextStepRelatedGroup]") -> "FT":
    """ "Related to your next step" — ZPD-recommended Kus + vector neighbours.

    Each group is ``{"ku": {uid, title}, "related": [node dicts]}``: the
    next-step Ku comes from the user's ZPD proximal zone (readiness-ranked,
    authored-edge traversal); the trailing chips are undirected vector-similarity
    hints, explicitly labeled "related (unordered)" so they read as invitations,
    never as curriculum order. Read-time lens — nothing is persisted.

    Empty input collapses to an empty div so the section vanishes entirely.
    """
    # Fail-soft like every layer of this fragment: a malformed group (missing
    # or empty ku/uid) collapses out rather than 500ing the PS detail page.
    items = [g for g in groups if g.get("ku", {}).get("uid")]
    if not items:
        return Div(id="ps-next-step-fragment")

    def _chip(node: "RelatedConceptChip", *, emphasis: bool = False) -> "FT":
        base = (
            "inline-flex items-center px-3 py-1.5 rounded-full border "
            "text-13 font-medium hover:bg-accent hover:text-accent-foreground "
        )
        tone = (
            "border-strength-core/50 bg-strength-core/10 text-foreground"
            if emphasis
            else "border-border bg-muted/40 text-foreground"
        )
        return A(node["title"] or node["uid"], href=f"/explore/ku/{node['uid']}", cls=base + tone)

    rows = []
    for group in items:
        ku = group["ku"]
        related = [r for r in group.get("related", []) if r.get("uid")]
        rows.append(
            Div(
                _chip(ku, emphasis=True),
                *(
                    [
                        Span(
                            "related (unordered):",
                            cls="text-11 text-muted-foreground font-mono self-center",
                        ),
                        *[_chip(r) for r in related],
                    ]
                    if related
                    else []
                ),
                cls="flex flex-wrap gap-2 items-center",
            )
        )

    return Section(
        section_label("Related to your next step", tag=H2, id="ps-next-step-h"),
        P(
            "Your readiest next concepts (from what you've engaged), each with "
            "unordered related hints — not a prescribed sequence.",
            cls="text-xs text-muted-foreground mb-3",
        ),
        Div(*rows, cls="flex flex-col gap-2.5"),
        id="ps-next-step-fragment",
        cls="mt-[24px]",
        role="region",
        **{"aria-labelledby": "ps-next-step-h"},
    )


# ---------------------------------------------------------------------------
# Tasks section
# ---------------------------------------------------------------------------


def _tasks_section(uid: str) -> "FT":
    """HTMX-loaded tasks section — shows tasks spawned from this PathStep.

    Loads on page render; reloads on `ps-engaged` custom event so newly
    spawned tasks appear immediately after "Start learning" engages the PS.
    """
    return Section(
        section_label("Tasks from this step", tag=H2, id="ps-tasks-h"),
        Div(
            id="ps-tasks-fragment",
            **{
                "hx-get": f"/explore/ps/{uid}/tasks",
                "hx-trigger": "load, ps-engaged",
                "hx-swap": "outerHTML",
            },
        ),
        cls="mt-[24px]",
        role="region",
        **{"aria-labelledby": "ps-tasks-h"},
    )


# ---------------------------------------------------------------------------
# Learning loop section
# ---------------------------------------------------------------------------


def _learning_loop_section(uid: str) -> "FT":
    """HTMX-loaded exercises + submissions section for authenticated users.

    Lazy-loads on page render. Exercises show status (submitted/reviewed/open);
    submissions show feedback from teacher/AI.
    """
    return Section(
        section_label("Exercises", tag=H2, id="ps-exercises-h"),
        Div(
            id="ps-exercises-fragment",
            **{
                "hx-get": f"/learning-loop/ps/{uid}/exercises",
                "hx-trigger": "load",
                "hx-swap": "outerHTML",
            },
        ),
        section_label("Submissions & Feedback", tag=H2, id="ps-submissions-h", cls="mt-[18px]"),
        Div(
            id="ps-submissions-fragment",
            **{
                "hx-get": f"/learning-loop/ps/{uid}/submissions-and-feedback",
                "hx-trigger": "load",
                "hx-swap": "outerHTML",
            },
        ),
        cls="mt-[24px]",
        role="region",
        **{"aria-labelledby": "ps-exercises-h"},
    )


# ---------------------------------------------------------------------------
# Blocking dependencies accordion
# ---------------------------------------------------------------------------


def _deps_accordion() -> "FT":
    panel_id = "deps-panel"
    return Section(
        Button(
            # Status tile
            Span(
                Icon("check", cls="w-[15px] h-[15px]", stroke_width="2.2"),
                cls="w-7 h-7 rounded-md flex items-center justify-center flex-none bg-priority-low/15 text-priority-low",
                **{
                    "x-show": "allMet",
                },
            ),
            Span(
                Icon("lock", cls="w-[15px] h-[15px]", stroke_width="2.2"),
                cls="w-7 h-7 rounded-md flex items-center justify-center flex-none bg-destructive/10 text-destructive",
                **{
                    "x-show": "!allMet",
                },
            ),
            # Summary text
            Span(
                Span(
                    "Blocking dependencies",
                    cls="block text-13 font-bold",
                    id="deps-h",
                ),
                Span(
                    "",
                    cls="block text-xs font-semibold mt-px",
                    **{
                        "x-text": (
                            "allMet "
                            "? 'Ready — nothing blocks this step.' "
                            ": (blockedCount + ' prerequisite' + (blockedCount === 1 ? '' : 's') + ' to clear')"
                        ),
                        ":class": "allMet ? 'text-priority-low' : 'text-destructive'",
                    },
                ),
                cls="flex-1 min-w-0",
            ),
            # Chevron
            Span(
                Icon("chevron-up", cls="w-[18px] h-[18px]", **{"x-show": "depsOpen"}),  # type: ignore[arg-type]  # boundary: fasthtml-elements
                Icon("chevron-down", cls="w-[18px] h-[18px]", **{"x-show": "!depsOpen"}),  # type: ignore[arg-type]  # boundary: fasthtml-elements
                cls="text-muted-foreground flex-none",
            ),
            type="button",
            cls="w-full flex items-center gap-2.5 px-5 py-[15px] text-left",
            **{
                "@click": "depsOpen = !depsOpen",
                ":aria-expanded": "depsOpen.toString()",
                "aria-controls": panel_id,
            },
        ),
        # Panel — deps list (empty state shown when blocking=[])
        Div(
            P(
                "No prerequisites defined for this step.",
                cls="text-13 leading-[1.55] text-muted-foreground",
                **{"x-show": "blocking.length === 0"},
            ),
            Ul(
                # x-for MUST live on a <template> — on a live element Alpine
                # evaluates the children's `dep.*` expressions unscoped
                # (ReferenceError: dep is not defined on every page load).
                Template(
                    Li(
                        Span(
                            Icon("check", cls="w-3 h-3", stroke_width="2.4"),
                            cls="w-[22px] h-[22px] rounded-md flex items-center justify-center flex-none bg-priority-low/15 text-priority-low",
                            **{
                                "x-show": "dep.status === 'met'",
                            },
                        ),
                        Span(
                            Icon("lock", cls="w-3 h-3", stroke_width="2.4"),
                            cls="w-[22px] h-[22px] rounded-md flex items-center justify-center flex-none bg-destructive/10 text-destructive",
                            **{
                                "x-show": "dep.status !== 'met'",
                            },
                        ),
                        A(
                            "",
                            cls="flex-1 text-13 font-semibold text-foreground/85 hover:underline",
                            **{
                                ":href": "'/explore/ps/' + dep.uid",
                                "x-text": "dep.title",
                            },
                        ),
                        Span(
                            "",
                            cls="font-mono text-10 font-semibold uppercase tracking-wider",
                            **{
                                "x-text": "dep.status === 'met' ? 'Completed' : 'Blocked'",
                                ":class": "dep.status === 'met' ? 'text-priority-low' : 'text-destructive'",
                            },
                        ),
                        cls="flex items-center gap-2.5 px-3 py-2.5 border border-border rounded-lg bg-muted/40",
                    ),
                    **{"x-for": "dep in blocking", ":key": "dep.uid"},
                ),
                cls="flex flex-col gap-2",
                **{"x-show": "blocking.length > 0"},
            ),
            id=panel_id,
            cls="px-5 pb-[18px]",
            **{
                "x-show": "depsOpen",
                "x-transition:enter": "transition ease-out duration-180",
                "x-transition:enter-start": "opacity-0",
                "x-transition:enter-end": "opacity-100",
                "x-transition:leave": "transition ease-in duration-120",
                "x-transition:leave-start": "opacity-100",
                "x-transition:leave-end": "opacity-0",
            },
        ),
        cls="mt-[18px] bg-card border border-border rounded-[12px] overflow-hidden",
        role="region",
        **{"aria-labelledby": "deps-h"},
    )


__all__ = [
    "render_ps_detail_content",
    "render_ps_next_step_related",
    "render_ps_not_found",
    "render_ps_related_concepts",
]
