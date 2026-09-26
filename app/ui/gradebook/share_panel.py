"""The Share panel — an owner shares a UserEntry with groups and people (Submit & Share arc R2, R7, R8).

Two pieces, both server-rendered:

- ``ShareButton`` sits on the owner's ``/gradebook/{uid}`` page (and is the
  target of the exchange thread's per-version "Share" link, which opens it
  through ``?share=1``). It is an Alpine-controlled modal whose body is
  HTMX-loaded from ``GET /gradebook/{uid}/share-panel`` the first time it is
  shown, so the page render pays nothing for it. A ``preselect`` token rides
  through to that load: the GradeBook's "Share your revised work" nudge opens
  the page with ``?share=1&preselect=reviewers``.
- ``SharePanelForm`` is that body: one checkbox per candidate group and
  person (the vocabulary values ``group:<uid>`` / ``user:<username>``), the
  ones the entry already reaches checked and disabled, posting to
  ``POST /api/user-entries/{uid}/share``. With ``preselect=reviewers`` the
  groups the entry was submitted to for feedback (``reviewer_group_uids``)
  render checked — among the offered groups only, and never one already
  shared; any other token preselects nothing. The response re-renders the
  form with the outcome line above it. Stop sharing lives on Your wall, not
  here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from fasthtml.common import H3, A, Button, Div, Form, Input, Label, P, Span

from core.models.user_entry.audience import GROUP_PREFIX, USER_PREFIX
from ui.components import ButtonT, Icon
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.modal import AlpineModal

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.ports.query_types import ShareCandidates
    from core.services.user_entry.audience_resolver import ShareOutcome

SHARE_PANEL_BODY_ID = "share-panel-body"
WALL_URL = "/profile/shared#your-wall"
PRESELECT_PARAM = "preselect"
PRESELECT_REVIEWERS = "reviewers"
"""The one ``preselect`` token: check the groups the entry was submitted to for feedback."""

_NOBODY_TO_SHARE_WITH = (
    "No groups or classmates to share with yet — join a group, or ask a teacher to add you."
)


def ShareButton(entry_uid: str, *, open: bool = False, preselect: str | None = None) -> Div:
    """The "Share" button and its modal, for the entry's owner.

    Args:
        entry_uid: The owned entry.
        open: Render the modal open (``?share=1`` — the exchange thread's
            per-version Share link and the GradeBook nudge land here).
        preselect: The ``preselect`` token forwarded to the panel load
            (``reviewers`` from the nudge); ``None`` preselects nothing.
    """
    body = Div(
        P("Loading…", cls="text-sm text-muted-foreground"),
        id=SHARE_PANEL_BODY_ID,
        # The token is percent-encoded into the query; the path stays a literal
        # the hx-target scan can read.
        hx_get=(
            f"/gradebook/{entry_uid}/share-panel?{urlencode({PRESELECT_PARAM: preselect})}"
            if preselect
            else f"/gradebook/{entry_uid}/share-panel"
        ),
        hx_trigger="intersect once",
        hx_swap="innerHTML",
    )
    return Div(
        Button(
            Icon("share-2", cls="size-4"),
            Span("Share", cls="ml-1"),
            type="button",
            cls=f"{ButtonT.default} inline-flex items-center",
            **{"@click": "shareOpen = true"},
        ),
        AlpineModal(
            Div(
                H3("Share this entry", cls="text-lg font-semibold"),
                Button(
                    Icon("x", cls="size-4"),
                    type="button",
                    aria_label="Close",
                    cls="text-muted-foreground hover:text-foreground",
                    **{"@click": "shareOpen = false"},
                ),
                cls="flex items-center justify-between mb-4",
            ),
            body,
            show="shareOpen",
            close="shareOpen = false",
            max_width="max-w-lg",
            scrollable=True,
            id="share-panel",
        ),
        **{"x-data": f"{{ shareOpen: {'true' if open else 'false'} }}"},
        cls="mb-4",
    )


def _candidate_row(
    value: str, label: str, *, shared: bool, preselected: bool = False, hint: str | None = None
) -> Div:
    """One checkbox row; an already-shared target is checked and disabled, a preselected one checked."""
    checkbox_id = f"share-{value.replace(':', '-')}"
    attrs: dict[str, object] = {
        "type": "checkbox",
        "name": "audience",
        "value": value,
        "id": checkbox_id,
        "cls": "h-4 w-4 rounded-sm border-input",
    }
    if shared:
        attrs["checked"] = True
        attrs["disabled"] = True
    elif preselected:
        attrs["checked"] = True
    return Div(
        Input(**attrs),
        Label(
            label,
            Span(f" @{hint}", cls="text-muted-foreground") if hint else "",
            fr=checkbox_id,
            cls="ml-2 text-sm",
        ),
        Badge("shared", variant=BadgeT.outline, size=Size.sm, cls="ml-2") if shared else "",
        cls="flex items-center py-1",
    )


def _group(title: str, rows: list[Div]) -> Div | str:
    if not rows:
        return ""
    return Div(
        P(title, cls="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1"),
        *rows,
        cls="mb-4",
    )


def SharePanelOutcome(outcome: ShareOutcome | None, error: str | None = None) -> FT | str:
    """The line above the form after a POST: what landed, what was refused."""
    if error:
        return P(error, cls="text-sm text-destructive mb-3", role="alert")
    if outcome is None:
        return ""
    landed = len(outcome.shared_groups) + len(outcome.shared_users)
    bits: list[str] = []
    if landed:
        bits.append(f"Shared with {landed} {'target' if landed == 1 else 'targets'}.")
    if outcome.newly_shared_users:
        bits.append(f"{len(outcome.newly_shared_users)} notified.")
    if outcome.failed:
        bits.append("Refused: " + "; ".join(f"{t}: {r}" for t, r in outcome.failed))
    return P(" ".join(bits), cls="text-sm mb-3", role="status") if bits else ""


def SharePanelForm(
    entry_uid: str,
    candidates: ShareCandidates,
    *,
    outcome: ShareOutcome | None = None,
    error: str | None = None,
    preselect: str | None = None,
) -> Div:
    """The modal body: candidates as checkboxes, posting the chosen vocabulary values.

    ``preselect=reviewers`` checks the offered groups the entry was submitted
    to for feedback (the class that reviewed it) that are not shared yet;
    nothing outside ``candidates["groups"]`` is ever checked.
    """
    shared_groups = set(candidates["shared_group_uids"])
    shared_users = set(candidates["shared_user_uids"])
    preselected_groups = (
        set(candidates["reviewer_group_uids"]) if preselect == PRESELECT_REVIEWERS else set()
    )
    group_rows = [
        _candidate_row(
            f"{GROUP_PREFIX}{g['uid']}",
            g["name"],
            shared=g["uid"] in shared_groups,
            preselected=g["uid"] in preselected_groups,
        )
        for g in candidates["groups"]
    ]
    people_rows = [
        _candidate_row(
            f"{USER_PREFIX}{p['username']}",
            p["display_name"] or p["username"] or p["uid"],
            shared=p["uid"] in shared_users,
            hint=p["username"],
        )
        for p in candidates["people"]
        if p["username"]
    ]
    if not group_rows and not people_rows:
        return Div(
            SharePanelOutcome(outcome, error),
            P(_NOBODY_TO_SHARE_WITH, cls="text-sm text-muted-foreground"),
        )
    return Div(
        SharePanelOutcome(outcome, error),
        Form(
            _group("Groups", group_rows),
            _group("People", people_rows),
            Div(
                Button("Share", type="submit", cls=ButtonT.primary),
                A(
                    "Stop sharing on Your wall →",
                    href=WALL_URL,
                    cls="text-xs text-muted-foreground ml-3 hover:underline",
                ),
                cls="flex items-center",
            ),
            hx_post=f"/api/user-entries/{entry_uid}/share",
            hx_target=f"#{SHARE_PANEL_BODY_ID}",
            hx_swap="innerHTML",
        ),
    )


__all__ = [
    "PRESELECT_PARAM",
    "PRESELECT_REVIEWERS",
    "SHARE_PANEL_BODY_ID",
    "WALL_URL",
    "ShareButton",
    "SharePanelForm",
    "SharePanelOutcome",
]
