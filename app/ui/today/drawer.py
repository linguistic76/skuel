"""HTMX fragment body for the Today drawer.

The drawer panel ships as static markup inside ``TodayPage`` (the "Connects"
block and action buttons). This fragment is swapped into ``#drawer-body``
when the drawer opens, carrying richer server-derived context that the
Alpine state doesn't already hold — full description, linked KUs, etc.

Wired to ``GET /today/tasks/{id}/drawer`` in
``adapters/inbound/today_routes.py`` (Phase 4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fasthtml.common import Div, P

from ui.primitives import section_label

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.task.task import Task


def render_task_drawer_body(task: Task) -> FT:
    """Return the HTMX fragment for the Today drawer body.

    The outer ``<div id="drawer-body">`` is in the page shell; this returns
    its inner content. Keep the fragment self-contained — no external
    styles beyond what Tailwind resolves globally.
    """
    description = (task.description or "").strip()

    if not description:
        return Div(
            P(
                "No additional detail captured for this node.",
                cls="text-xs leading-snug text-muted-foreground italic",
            ),
        )

    return Div(
        section_label("Details"),
        P(
            description,
            cls="text-13 leading-relaxed text-foreground whitespace-pre-wrap",
        ),
    )


__all__ = ["render_task_drawer_body"]
