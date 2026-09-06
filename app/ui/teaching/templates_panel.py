"""
Teacher-only Activity Templates panel embedded on the PS detail page.

Renders the templates currently attached to a PathStep, grouped by Activity
Domain. The panel is **read-only** — templates are authored as ``_tmpl.md``
files in the content vault and attached by the PathStep's
``{domain}_template_uids:`` frontmatter, so there is nothing to add, edit or
detach here.

The wrapper id ``TEMPLATES_PANEL_ID`` is stable so the HTMX load targets a
known node.

See: /docs/guides/ACTIVITY_TEMPLATE_AUTHORING.md
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import H3, H4, Code, Div, Li, P, Span, Ul

from ui.feedback import Badge, BadgeT
from ui.layout import Size

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
    """Render the read-only templates panel for a PathStep.

    Args:
        ps_uid: PathStep UID — identifies the panel in the rendered markup.
        attached: ``{domain: [template_props_dict, ...]}``. Each dict carries
            at minimum ``uid`` and ``title``. Missing domains render as empty.
    """
    rows = [
        _render_domain_row(domain, label, attached.get(domain, []))
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
            P(
                "Authored in the content vault as ",
                Code("_tmpl.md", cls="text-xs"),
                " files and attached by this step's ",
                Code("{domain}_template_uids:", cls="text-xs"),
                " frontmatter.",
                cls="text-xs text-muted-foreground mt-1",
            ),
            cls="mb-4",
        ),
        Div(*rows, cls="space-y-3"),
        id=TEMPLATES_PANEL_ID,
        data_ps_uid=ps_uid,
        cls="rounded-lg border border-border bg-card p-5 mt-8",
    )


def _render_domain_row(
    domain: str,
    label: str,
    templates: list[dict[str, Any]],
) -> Any:
    """One domain's subsection: header + list of attached templates."""
    header = Div(
        H4(label, cls="text-sm font-medium"),
        Badge(
            str(len(templates)),
            variant=BadgeT.neutral,
            size=Size.sm,
            cls="ml-2",
        ),
        cls="flex items-center",
    )

    body: Any
    if not templates:
        body = P(
            f"No {label.lower()} templates yet.",
            cls="text-xs text-muted-foreground italic mt-1",
        )
    else:
        body = Ul(
            *[_render_template_row(t) for t in templates],
            cls="mt-2 space-y-1",
        )

    return Div(
        header,
        body,
        data_domain=domain,
        cls="border-b border-border last:border-b-0 pb-3 last:pb-0",
    )


def _render_template_row(template: dict[str, Any]) -> Any:
    """One template row: title + its authored UID."""
    uid = str(template.get("uid", ""))
    title = str(template.get("title") or uid)

    return Li(
        Span(title, cls="text-sm flex-1 min-w-0 truncate"),
        Code(uid, cls="text-xs text-muted-foreground shrink-0"),
        cls="flex items-center justify-between gap-3 px-2 py-1 rounded-sm hover:bg-muted/40",
    )


def render_templates_panel_placeholder(ps_uid: str) -> Any:
    """HTMX-load placeholder that fetches the panel fragment on-load.

    Rendered on the PS detail page for TEACHER+ viewers; the fragment route
    (``GET /teaching/ps/{ps_uid}/templates``) enforces the same gate.
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
