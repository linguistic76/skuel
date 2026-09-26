"""The recipient card — what a UserEntry looks like to someone it was shared with.

Rendered by ``GET /gradebook/{uid}`` when the viewer is not the entry's owner
(Submit & Share arc R6): title, description, who it is from, when, the badges
and a link to open the file. The badges are the fixed "Shared with you" and
the entry's derived review standing ("Revised after feedback", "Reviewed ·
Teacher/AI" — R2, ``ui/gradebook/review_badges.py``): that the work went
through review, never the verdict. Never the status, the processed body,
feedback reports or the exchange thread — those are the owner's view. Access
is decided by the route's audience read; this module is pure presentation and
performs no check of its own.

See: /docs/decisions/ADR-088-submit-and-share.md §3
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fasthtml.common import Div, P

from ui.components import ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.feedback import Badge, BadgeT
from ui.gradebook.review_badges import review_badges
from ui.layout import Size
from ui.patterns.page_header import PageHeader
from ui.patterns.relative_time import format_relative_time
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.user_entry.user_entry import UserEntry
    from core.ports.query_types import ReviewStanding

SHARED_WITH_YOU_LABEL = "Shared with you"
"""The recipient card's fixed badge; the derived "reviewed" badges sit beside it."""


def _attribution(entry: UserEntry, from_name: str | None) -> str:
    when = format_relative_time(entry.created_at)
    bits: list[str] = []
    if from_name:
        bits.append(f"From {from_name}")
    if when:
        bits.append(when)
    return " · ".join(bits)


def RecipientEntryCard(
    entry: UserEntry, from_name: str | None, standing: ReviewStanding | None = None
) -> FT:
    """The R6 card for a viewer the share links admit.

    Args:
        entry: The shared entry (the route already decided the viewer may open it).
        from_name: The owner's display name, or ``None`` when it could not be
            resolved — the card then carries no "From" line rather than a uid.
        standing: The entry's derived review standing (its "reviewed" badges);
            ``None`` renders "Shared with you" alone.
    """
    description = entry.description or entry.summary or ""
    return Div(
        PageHeader(entry.title or "Shared entry", subtitle=_attribution(entry, from_name)),
        Card(
            CardHeader(
                Div(
                    CardTitle("Shared entry"),
                    Div(
                        *review_badges(standing),
                        Badge(SHARED_WITH_YOU_LABEL, variant=BadgeT.outline, size=Size.sm),
                        cls="flex flex-wrap items-center justify-end gap-1",
                    ),
                    cls="flex items-center justify-between gap-2",
                ),
            ),
            CardBody(
                P(description, cls="text-sm whitespace-pre-wrap")
                if description
                else P("No description.", cls="text-sm text-muted-foreground"),
                Div(
                    ButtonLink(
                        "Open file (.md)",
                        href=f"/gradebook/{entry.uid}/download",
                        cls=ButtonT.primary,
                    ),
                    # Two ways back: a person share is listed on the Shared page, a
                    # group share on the Groups hub (its tab is where the tile was).
                    ButtonLink("← Shared with you", href="/profile/shared", cls=ButtonT.ghost),
                    ButtonLink("← Groups", href="/groups", cls=ButtonT.ghost),
                    cls="mt-4 flex flex-wrap gap-2",
                ),
            ),
            cls="bg-background shadow-xs",
        ),
    )


__all__ = ["SHARED_WITH_YOU_LABEL", "RecipientEntryCard"]
