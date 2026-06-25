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
    Script,
    Section,
    Span,
    Ul,
)
from monsterui.franken import UkIcon

from core.models.enums import UserRole

if TYPE_CHECKING:
    from fasthtml.common import FT

_COLUMN_CLS = "mx-auto max-w-[760px] px-5 pt-8 pb-20"


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def render_ps_not_found(uid: str) -> Div:
    """Render the not-found state for a PathStep detail fragment."""
    return Div(
        A(
            UkIcon("arrow-left", cls="w-3.5 h-3.5"),
            " Explore",
            href="/explore",
            cls="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-muted-foreground hover:text-foreground mb-6",
        ),
        Div(
            P("Path step not found.", cls="text-[14px] font-semibold text-foreground"),
            P(f"No path step with ID: {uid}", cls="text-[13px] text-muted-foreground mt-1"),
            A(
                "← Back to Explore",
                href="/explore",
                cls="inline-flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground hover:text-foreground mt-4",
            ),
            cls="p-8 border border-border rounded-xl bg-card text-center",
        ),
        id="ps-detail-content",
        cls=_COLUMN_CLS,
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
        user_role: Viewer's role — gates teacher-only controls.
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
        "blocking": [],  # populated via orchestrator in a future iteration
        "prev_step": None,
        "next_step": None,
    }
    seed_json = (
        json.dumps(seed, default=str)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    return Div(
        Script(NotStr(f"window.PS_SEED = {seed_json};")),
        _back_link(),
        _hero_card(step, uid, user_uid),
        _body_section(content_html) if content_html else Div(),
        _deps_accordion(),
        _footer_nav(),
        id="ps-detail-content",
        cls=_COLUMN_CLS,
        **{"x-data": "pathstep(window.PS_SEED)"},
    )


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


def _back_link() -> "FT":
    return A(
        UkIcon("arrow-left", cls="w-[15px] h-[15px]"),
        " Explore",
        href="/explore",
        cls="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-muted-foreground hover:text-foreground mb-[18px]",
    )


def _footer_nav() -> "FT":
    return Div(
        A(
            UkIcon("arrow-left", cls="w-4 h-4"),
            " Back to Explore",
            href="/explore",
            cls="inline-flex items-center gap-2 text-[13px] font-medium text-muted-foreground hover:text-foreground",
        ),
        cls="mt-9 flex items-center",
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
                cls="text-[30px] font-extrabold leading-[1.12] tracking-[-0.02em]",
            ),
            # Description/central idea
            P(
                description,
                cls="mt-[13px] text-[16px] leading-[1.55] text-foreground/75 max-w-[62ch]",
            )
            if description
            else Div(),
            # Meta chips
            _meta_chips(est_minutes, tags),
            cls="px-8 pt-[30px] pb-[26px]",
        ),
        # Action bar (authenticated users only)
        _action_bar(uid) if user_uid else _unauthenticated_cta(),
        cls="bg-card border border-border rounded-xl shadow-[0_1px_3px_rgba(0,0,0,0.04)] overflow-hidden",
        role="region",
        **{"aria-labelledby": "ps-title"},
    )


def _kind_badge() -> "FT":
    return Span(
        UkIcon("route", cls="w-[13px] h-[13px]"),
        " Path step",
        cls=(
            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md "
            "bg-muted text-muted-foreground "
            "text-[10.5px] font-bold uppercase tracking-[0.08em] whitespace-nowrap"
        ),
    )


def _bookmark_btn(uid: str) -> "FT":
    return Button(
        UkIcon("bookmark", cls="w-3.5 h-3.5"),
        Span("", **{"x-text": "bookmarked ? 'Saved' : 'Save'"}),
        type="button",
        cls=(
            "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md "
            "text-[12px] font-semibold border transition-colors "
            "focus:outline-none focus:shadow-focus"
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
                UkIcon("clock", cls="w-3.5 h-3.5"),
                f" {est_minutes} min",
                cls="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-muted-foreground",
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
                    cls="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-foreground/85",
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
                cls="h-full rounded-full bg-strength-core transition-[width] duration-[350ms] ease-out",
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
                    cls="inline-flex items-center gap-1.5 text-[13px] font-semibold text-muted-foreground whitespace-nowrap",
                    **{"x-show": "status === 'not_started'"},
                ),
                # learning
                Span(
                    Span(cls="w-2 h-2 rounded-full bg-warning"),
                    " Learning",
                    cls="inline-flex items-center gap-1.5 text-[13px] font-semibold text-warning whitespace-nowrap",
                    **{"x-show": "status === 'learning'"},
                ),
                # read / completed
                Span(
                    UkIcon("check", cls="w-[15px] h-[15px]"),
                    " Completed",
                    cls="inline-flex items-center gap-1.5 text-[13px] font-semibold text-priority-low whitespace-nowrap",
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
                    UkIcon("arrow-right", cls="w-[15px] h-[15px]"),
                    type="button",
                    cls=(
                        "inline-flex items-center gap-2 px-[18px] py-[9px] rounded-lg "
                        "bg-primary text-primary-foreground "
                        "text-[13.5px] font-semibold hover:opacity-90 "
                        "focus:outline-none focus:shadow-focus whitespace-nowrap"
                    ),
                    **{
                        "x-show": "status !== 'read'",
                        "@click": "advance()",
                    },
                ),
                # Review again (read state)
                Button(
                    UkIcon("rotate-ccw", cls="w-3.5 h-3.5"),
                    " Review again",
                    type="button",
                    cls=(
                        "inline-flex items-center gap-1.5 px-4 py-[9px] rounded-lg "
                        "border border-border bg-card "
                        "text-[13px] font-semibold text-foreground/80 "
                        "hover:bg-muted focus:outline-none focus:shadow-focus"
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
            UkIcon("arrow-right", cls="w-[15px] h-[15px]"),
            href="/login",
            cls=(
                "inline-flex items-center gap-2 px-[18px] py-[9px] rounded-lg "
                "bg-primary text-primary-foreground "
                "text-[13.5px] font-semibold hover:opacity-90"
            ),
        ),
        cls="border-t border-border bg-muted/40 px-8 py-4 flex justify-end",
    )


# ---------------------------------------------------------------------------
# Body content
# ---------------------------------------------------------------------------


def _body_section(content_html: str) -> "FT":
    return Section(
        H2(
            "The idea",
            id="idea-h",
            cls="text-[11px] font-bold uppercase tracking-[0.09em] text-muted-foreground mb-3",
        ),
        Div(NotStr(content_html), cls="skuel-prose"),
        cls="mt-[30px]",
        role="region",
        **{"aria-labelledby": "idea-h"},
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
                UkIcon("check", cls="w-[15px] h-[15px]", stroke_width="2.2"),
                cls="w-7 h-7 rounded-md flex items-center justify-center flex-none bg-priority-low/15 text-priority-low",
                **{
                    "x-show": "allMet",
                },
            ),
            Span(
                UkIcon("lock", cls="w-[15px] h-[15px]", stroke_width="2.2"),
                cls="w-7 h-7 rounded-md flex items-center justify-center flex-none bg-destructive/10 text-destructive",
                **{
                    "x-show": "!allMet",
                },
            ),
            # Summary text
            Span(
                Span(
                    "Blocking dependencies",
                    cls="block text-[13.5px] font-bold",
                    id="deps-h",
                ),
                Span(
                    "",
                    cls="block text-[12px] font-semibold mt-px",
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
                UkIcon("chevron-up", cls="w-[18px] h-[18px]", **{"x-show": "depsOpen"}),
                UkIcon("chevron-down", cls="w-[18px] h-[18px]", **{"x-show": "!depsOpen"}),
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
                cls="text-[13px] leading-[1.55] text-muted-foreground",
                **{"x-show": "blocking.length === 0"},
            ),
            Ul(
                Li(
                    Span(
                        UkIcon("check", cls="w-3 h-3", stroke_width="2.4"),
                        cls="w-[22px] h-[22px] rounded-md flex items-center justify-center flex-none bg-priority-low/15 text-priority-low",
                        **{
                            "x-show": "dep.status === 'met'",
                        },
                    ),
                    Span(
                        UkIcon("lock", cls="w-3 h-3", stroke_width="2.4"),
                        cls="w-[22px] h-[22px] rounded-md flex items-center justify-center flex-none bg-destructive/10 text-destructive",
                        **{
                            "x-show": "dep.status !== 'met'",
                        },
                    ),
                    A(
                        "",
                        cls="flex-1 text-[13px] font-semibold text-foreground/85 hover:underline",
                        **{
                            ":href": "'/explore/ps/' + dep.uid",
                            "x-text": "dep.title",
                        },
                    ),
                    Span(
                        "",
                        cls="font-mono text-[10.5px] font-semibold uppercase tracking-[0.05em]",
                        **{
                            "x-text": "dep.status === 'met' ? 'Completed' : 'Blocked'",
                            ":class": "dep.status === 'met' ? 'text-priority-low' : 'text-destructive'",
                        },
                    ),
                    cls="flex items-center gap-2.5 px-3 py-2.5 border border-border rounded-lg bg-muted/40",
                    **{"x-for": "dep in blocking", ":key": "dep.uid"},
                ),
                cls="flex flex-col gap-2",
                **{"x-show": "blocking.length > 0"},
            ),
            id=panel_id,
            cls="px-5 pb-[18px]",
            **{
                "x-show": "depsOpen",
                "x-transition:enter": "transition ease-out duration-[180ms]",
                "x-transition:enter-start": "opacity-0",
                "x-transition:enter-end": "opacity-100",
                "x-transition:leave": "transition ease-in duration-[120ms]",
                "x-transition:leave-start": "opacity-100",
                "x-transition:leave-end": "opacity-0",
            },
        ),
        cls="mt-[18px] bg-card border border-border rounded-xl overflow-hidden",
        role="region",
        **{"aria-labelledby": "deps-h"},
    )


__all__ = ["render_ps_detail_content", "render_ps_not_found"]
