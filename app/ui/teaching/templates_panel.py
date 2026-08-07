"""
Teacher-only Activity Templates panel embedded on the PS detail page.

Renders the templates currently attached to a PathStep, grouped by Activity
Domain. Each domain row offers:

- "+ Add" — link to the create form (full page at
  ``/teaching/ps/{ps_uid}/templates/{domain}/new``).
- Per-template "Edit" link + "Detach" inline form (POST). Detach returns this
  same panel fragment so the list refreshes in place.

The wrapper id ``TEMPLATES_PANEL_ID`` is stable so detach/refresh HTMX swaps
target the right node.
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import H3, H4, Button, Div, Form, Li, P, Span, Ul

from ui.components import ButtonT
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.csrf import csrf_hidden_input
from ui.primitives import ButtonLink

TEMPLATES_PANEL_ID = "ps-templates-panel"

# Source of truth for the panel's six domain rows. Order matches the spawn
# order's layering (Choice/Habit/Principle → Goal → Event → Task) so the panel
# reads top-down from "context" templates toward "action" templates.
PANEL_DOMAINS: tuple[tuple[str, str], ...] = (
    ("principle", "Principles"),
    ("choice", "Choices"),
    ("habit", "Habits"),
    ("goal", "Goals"),
    ("event", "Events"),
    ("task", "Tasks"),
)


def render_templates_panel(
    ps_uid: str,
    attached: dict[str, list[dict[str, Any]]],
) -> Any:
    """Render the templates panel for a PathStep.

    Args:
        ps_uid: PathStep UID — used to build add/edit/detach URLs.
        attached: ``{domain: [template_props_dict, ...]}``. Each dict carries
            at minimum ``uid`` and ``title``. Missing domains render as empty.
    """
    rows = [
        _render_domain_row(ps_uid, domain, label, attached.get(domain, []))
        for domain, label in PANEL_DOMAINS
    ]

    return Div(
        Div(
            H3("Activity Templates", cls="text-base font-semibold"),
            P(
                "Templates spawn into each student's Activity Domains when they engage "
                "with this PathStep.",
                cls="text-sm text-muted-foreground",
            ),
            cls="mb-4",
        ),
        Div(*rows, cls="space-y-3"),
        id=TEMPLATES_PANEL_ID,
        cls="rounded-lg border border-border bg-card p-5 mt-8",
    )


def _render_domain_row(
    ps_uid: str,
    domain: str,
    label: str,
    templates: list[dict[str, Any]],
) -> Any:
    """One domain's subsection: header + add button + list of templates."""
    header = Div(
        Div(
            H4(label, cls="text-sm font-medium"),
            Badge(
                str(len(templates)),
                variant=BadgeT.neutral,
                size=Size.sm,
                cls="ml-2",
            ),
            cls="flex items-center",
        ),
        ButtonLink(
            "+ Add",
            href=f"/teaching/ps/{ps_uid}/templates/{domain}/new",
            cls=ButtonT.ghost,
            size="sm",
        ),
        cls="flex items-center justify-between",
    )

    body: Any
    if not templates:
        body = P(
            f"No {label.lower()} templates yet.",
            cls="text-xs text-muted-foreground italic mt-1",
        )
    else:
        body = Ul(
            *[_render_template_row(ps_uid, domain, t) for t in templates],
            cls="mt-2 space-y-1",
        )

    return Div(header, body, cls="border-b border-border last:border-b-0 pb-3 last:pb-0")


def _render_template_row(
    ps_uid: str,
    domain: str,
    template: dict[str, Any],
) -> Any:
    """One template row: title + edit link + detach inline form."""
    uid = str(template.get("uid", ""))
    title = str(template.get("title") or uid)

    detach_form = Form(
        csrf_hidden_input(),
        Button(
            "Detach",
            type="submit",
            cls=(
                "text-xs px-2 py-1 rounded-sm border border-border bg-background "
                "hover:bg-destructive/10 hover:text-destructive hover:border-destructive/40"
            ),
        ),
        method="POST",
        action=f"/teaching/ps/{ps_uid}/templates/{domain}/detach?uid={uid}",
        hx_post=f"/teaching/ps/{ps_uid}/templates/{domain}/detach?uid={uid}",
        hx_target=f"#{TEMPLATES_PANEL_ID}",
        hx_swap="outerHTML",
        hx_confirm=f"Detach {title} from this PathStep?",
        cls="inline",
    )

    return Li(
        Span(title, cls="text-sm flex-1 min-w-0 truncate"),
        Div(
            ButtonLink(
                "Edit",
                href=f"/teaching/ps/{ps_uid}/templates/{domain}/edit?uid={uid}",
                cls=ButtonT.ghost,
                size="sm",
            ),
            detach_form,
            cls="flex items-center gap-2 shrink-0",
        ),
        cls=("flex items-center justify-between gap-3 px-2 py-1 rounded-sm hover:bg-muted/40"),
    )


def render_templates_panel_placeholder(ps_uid: str) -> Any:
    """HTMX-load placeholder that fetches the panel fragment on-load.

    Drop this into the PS detail page (teacher-only) so the panel can be
    swapped in place after detach without refetching the whole detail page.
    """
    return Div(
        id=TEMPLATES_PANEL_ID,
        hx_get=f"/teaching/ps/{ps_uid}/templates",
        hx_trigger="load",
        hx_swap="outerHTML",
    )


__all__ = [
    "PANEL_DOMAINS",
    "TEMPLATES_PANEL_ID",
    "render_templates_panel",
    "render_templates_panel_placeholder",
]
