"""Publish state UI for the PathStep teacher flow (Slice 2).

Three renderers, used together to surface the teacher-side counterpart to
slice 1's student engagement flow on ``/explore/ps/{uid}``:

- :func:`render_status_badge` — Draft/Published indicator in the metadata
  row near the top of the page. Visible to every viewer. On a successful
  publish, the handler returns a fresh badge with ``hx_swap_oob="true"`` so
  HTMX replaces the in-page badge alongside the in-place swap of the
  publish-state wrapper.

- :func:`render_publish_state` — wrapper hosting the Publish button. Visible
  only when the viewer is TEACHER+ *and* the PS is DRAFT. The wrapper id is
  stable; non-teacher / non-DRAFT viewers get an empty wrapper so future
  Dismiss → restore swaps still have a target.

- :func:`render_publish_violations` — replaces the publish button with a
  panel that lists every :class:`Violation` from
  ``Errors.ps_validation_report``, plus a Dismiss button that hx-GETs the
  publish-state wrapper back via ``/explore/ps/{uid}/publish-state``.

Wrapper IDs are exported so the route handlers and tests stay in sync.
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import H4, Div, Li, Span, Ul

from core.models.enums.learning_enums import KnowledgeStatus
from core.ports.query_types import Violation
from ui.buttons import Button, ButtonT
from ui.feedback import Badge, BadgeT
from ui.layout import Size

# Wrapper ids — referenced by route handlers (in-place + OOB swaps) and tests.
PUBLISH_STATE_ID = "ps-publish-state"
STATUS_BADGE_ID = "ps-status-badge"

# Variant per status — Draft reads as muted/incomplete, Published as success,
# Archived as muted, Under-review as warning.
_STATUS_VARIANT: dict[KnowledgeStatus, BadgeT] = {
    KnowledgeStatus.DRAFT: BadgeT.secondary,
    KnowledgeStatus.PUBLISHED: BadgeT.success,
    KnowledgeStatus.ARCHIVED: BadgeT.neutral,
    KnowledgeStatus.UNDER_REVIEW: BadgeT.warning,
}

# Human-facing labels — title-case for display in the metadata row.
_STATUS_LABEL: dict[KnowledgeStatus, str] = {
    KnowledgeStatus.DRAFT: "Draft",
    KnowledgeStatus.PUBLISHED: "Published",
    KnowledgeStatus.ARCHIVED: "Archived",
    KnowledgeStatus.UNDER_REVIEW: "Under Review",
}


def render_status_badge(status: KnowledgeStatus | None, oob: bool = False) -> Any:
    """Render the Draft/Published badge with id ``#ps-status-badge``.

    Args:
        status: The PS's current ``KnowledgeStatus``. ``None`` falls back to
            DRAFT — defensive default for legacy nodes missing the field.
        oob: If True, the badge carries ``hx-swap-oob="true"`` so HTMX
            replaces the in-page badge when the handler returns it alongside
            another swap (publish success).
    """
    if isinstance(status, str):
        try:
            status = KnowledgeStatus(status)
        except ValueError:
            status = KnowledgeStatus.DRAFT
    effective = status or KnowledgeStatus.DRAFT
    variant = _STATUS_VARIANT.get(effective, BadgeT.secondary)
    label = _STATUS_LABEL.get(effective, effective.value.title())

    kwargs: dict[str, Any] = {"id": STATUS_BADGE_ID}
    if oob:
        # HTMX out-of-band swap — replace the matching element on the page.
        kwargs["hx_swap_oob"] = "true"

    return Badge(
        Span("Status:", cls="font-medium mr-1"),
        label,
        variant=variant,
        size=Size.sm,
        cls="gap-1",
        **kwargs,
    )


def render_publish_state(uid: str, status: KnowledgeStatus | None, is_teacher: bool) -> Any:
    """Render the publish-button wrapper for a PathStep.

    Visible content is the Publish button only when the viewer is TEACHER+
    and the PS is DRAFT. Other cases return an empty wrapper preserving the
    same id — so Dismiss-from-violations can target it on restore.

    Args:
        uid: The PathStep uid (POST target).
        status: The PS's current status.
        is_teacher: Whether the viewer has TEACHER role or higher.
    """
    show_button = is_teacher and (status or KnowledgeStatus.DRAFT) == KnowledgeStatus.DRAFT
    body: Any
    if show_button:
        body = Button(
            "Publish",
            variant=ButtonT.primary,
            size=Size.sm,
            hx_post=f"/explore/ps/{uid}/publish",
            hx_swap="outerHTML",
            hx_target=f"#{PUBLISH_STATE_ID}",
        )
    else:
        body = None
    return Div(body, id=PUBLISH_STATE_ID, cls="flex items-center gap-2")


def render_publish_violations(uid: str, violations: list[Violation]) -> Any:
    """Render the validation-failure panel in place of the Publish button.

    Lists each violation with template title + type, the offending field, the
    violation kind, and the hint (if any). Dismiss restores the publish-state
    wrapper via the ``/publish-state`` route.
    """
    rows = [_violation_row(v) for v in violations]
    count = len(violations)
    heading = f"Cannot publish: {count} issue{'s' if count != 1 else ''}"
    return Div(
        H4(heading, cls="text-sm font-semibold mb-2"),
        Ul(*rows, cls="list-disc pl-5 space-y-1 mb-3 text-xs text-foreground"),
        Button(
            "Dismiss",
            variant=ButtonT.ghost,
            size=Size.sm,
            hx_get=f"/explore/ps/{uid}/publish-state",
            hx_swap="outerHTML",
            hx_target=f"#{PUBLISH_STATE_ID}",
        ),
        id=PUBLISH_STATE_ID,
        cls="border border-destructive/40 rounded-md p-3 bg-destructive/5",
    )


# Human-readable phrasing for each violation kind. Falls back to the raw
# enum value so future kinds still render something useful.
_VIOLATION_PHRASE: dict[str, str] = {
    "target_missing": "references a template not on this PathStep",
    "wrong_type": "references the wrong template type",
    "cycle": "would form a reference cycle",
    "cross_ps": "references a template on a different PathStep",
    "self_reference": "references itself",
}


def _violation_row(v: Violation) -> Any:
    """One bullet describing where the cross-template reference broke."""
    phrase = _VIOLATION_PHRASE.get(v["violation"], v["violation"])
    hint = f" (did you mean: {v['hint']}?)" if v.get("hint") else ""
    return Li(
        Span(f"{v['template_title']} ", cls="font-medium"),
        Span(f"[{v['template_type']}] ", cls="text-muted-foreground"),
        Span(f"— field {v['field']!r} {phrase}{hint}"),
    )


__all__ = [
    "PUBLISH_STATE_ID",
    "STATUS_BADGE_ID",
    "render_status_badge",
    "render_publish_state",
    "render_publish_violations",
]
