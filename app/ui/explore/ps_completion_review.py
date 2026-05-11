"""Completion review panel for the PathStep engagement lifecycle (Slice 4).

Renders the inline keep/discard form that replaces ``#ps-engagement-actions``
when the student clicks "Complete" on the engaged-state action group. The
form submits to ``POST /explore/ps/{uid}/complete``; Cancel restores the
engagement-actions group via ``GET /explore/ps/{uid}/engagement-actions``.

Defaults pinned 2026-05-11:
- All rows pre-checked as Keep — matches the service's "missing key = keep"
  default and the "exposure to possibilities" pedagogical principle.
- One row per ``template_uid`` (the service-contract granularity, not per
  instance). For now there's exactly one instance per template so the row's
  ``title`` comes from that single instance; if a future spawn fans out 1→N
  the row title can summarize.
"""

from __future__ import annotations

from fasthtml.common import H4, Div, Form, Input, P, Span

from core.services.ps_engagement.ps_engagement_service import ReviewItem
from ui.buttons import Button, ButtonT
from ui.feedback import Badge, BadgeT
from ui.forms.components import Checkbox
from ui.layout import Size

_ENGAGEMENT_ACTIONS_ID = "ps-engagement-actions"


def render_review_form(uid: str, items: list[ReviewItem]) -> Div:
    """Render the inline review form for a PathStep completion.

    Each row carries a hidden ``template_uids`` field (collected on submit)
    plus a checkbox named ``keep_{template_uid}``. The handler reads which
    template UIDs have ``keep_*`` present in the form payload and assembles
    the ``review: dict[str, ReviewDecision]`` for ``complete_pathstep``.

    The outer wrapper reuses ``id="ps-engagement-actions"`` so swaps return
    here cleanly via the same target the parent group uses.
    """
    body = _populated_review_body(uid, items) if items else _empty_review_body(uid)
    return Div(body, id=_ENGAGEMENT_ACTIONS_ID, cls="border border-border rounded-md p-4")


def render_review_error(uid: str, message: str) -> Div:
    """Render the review panel for an error case (Neo4j down, service failure).

    Keeps the same wrapper id so the failed POST swaps in place; gives the
    student a retry path back to the engagement-actions row.
    """
    return Div(
        Div(
            H4("Couldn't complete this engagement", cls="text-base font-semibold mb-2"),
            P(message, cls="text-sm text-muted-foreground mb-3"),
            Button(
                "Back to engagement",
                variant=ButtonT.ghost,
                size=Size.sm,
                hx_get=f"/explore/ps/{uid}/engagement-actions",
                hx_target=f"#{_ENGAGEMENT_ACTIONS_ID}",
                hx_swap="outerHTML",
            ),
            cls="flex flex-col gap-1",
        ),
        id=_ENGAGEMENT_ACTIONS_ID,
        cls="border border-destructive/40 rounded-md p-4",
    )


def _empty_review_body(uid: str) -> Div:
    """Engaged but nothing spawned (edge case — empty template set on PS).

    Surface an explicit message and let the student close the engagement with
    a single click; the service handles an empty review fine.
    """
    return Div(
        H4("Complete this engagement?", cls="text-base font-semibold mb-1"),
        P(
            "No activities were spawned by this PathStep — nothing to review.",
            cls="text-sm text-muted-foreground mb-3",
        ),
        Form(
            Div(
                Button(
                    "Cancel",
                    type="button",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    hx_get=f"/explore/ps/{uid}/engagement-actions",
                    hx_target=f"#{_ENGAGEMENT_ACTIONS_ID}",
                    hx_swap="outerHTML",
                ),
                Button(
                    "Complete",
                    type="submit",
                    variant=ButtonT.primary,
                    size=Size.sm,
                ),
                cls="flex gap-2 justify-end",
            ),
            hx_post=f"/explore/ps/{uid}/complete",
            hx_target=f"#{_ENGAGEMENT_ACTIONS_ID}",
            hx_swap="outerHTML",
        ),
    )


def _populated_review_body(uid: str, items: list[ReviewItem]) -> Div:
    rows = [_review_row(item) for item in items]
    return Div(
        H4("Review: What to keep?", cls="text-base font-semibold mb-1"),
        P(
            "Uncheck anything you'd rather not own. Kept items become yours; "
            "unchecked items are removed.",
            cls="text-xs text-muted-foreground mb-3",
        ),
        Form(
            Div(*rows, cls="flex flex-col gap-2 mb-4"),
            Div(
                Button(
                    "Cancel",
                    type="button",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    hx_get=f"/explore/ps/{uid}/engagement-actions",
                    hx_target=f"#{_ENGAGEMENT_ACTIONS_ID}",
                    hx_swap="outerHTML",
                ),
                Button(
                    "Save & Complete",
                    type="submit",
                    variant=ButtonT.primary,
                    size=Size.sm,
                ),
                cls="flex gap-2 justify-end",
            ),
            hx_post=f"/explore/ps/{uid}/complete",
            hx_target=f"#{_ENGAGEMENT_ACTIONS_ID}",
            hx_swap="outerHTML",
        ),
    )


def _review_row(item: ReviewItem) -> Div:
    """One template's keep/discard row + the hidden template_uid carry-field."""
    checkbox_name = f"keep_{item.template_uid}"
    return Div(
        Input(
            type="hidden",
            name="template_uids",
            value=item.template_uid,
        ),
        Div(
            Checkbox(
                id=checkbox_name,
                name=checkbox_name,
                value="keep",
                checked=True,
            ),
            Span(item.title, cls="text-sm font-medium ml-2"),
            Badge(item.label, variant=BadgeT.outline, size=Size.sm, cls="ml-2"),
            cls="flex items-center",
        ),
        cls="flex items-center justify-between gap-2 py-1",
    )
