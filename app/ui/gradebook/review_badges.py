"""The derived "reviewed" badges — one renderer for every surface that carries them.

An entry's standing is derived by the graph read (``ReviewStanding``), never
stored (ADR-088 §1, Submit & Share arc R2): "Reviewed · Teacher" / "Reviewed ·
AI" when an outcome-bearing report stands on it, "Revised after feedback"
when an earlier entry in the same exchange was reviewed before this one was
written. The Shared-with-you card, the wall row and the recipient card all
render them through ``review_badges`` — the badge says the work went through
review, never what the verdict was.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.enums.pipeline import ReportSource
from ui.feedback import Badge, BadgeT
from ui.layout import Size

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.ports.query_types import ReviewStanding

REVISED_AFTER_FEEDBACK_LABEL = "Revised after feedback"
REVIEWED_LABEL = "Reviewed"


def reviewed_label(source: str | None) -> str:
    """``Reviewed · Teacher`` / ``Reviewed · AI`` from the report source; a source this build does not know reads ``Reviewed``."""
    try:
        short = ReportSource(source).get_short_label() if source else ""
    except ValueError:
        short = ""
    return f"{REVIEWED_LABEL} · {short}" if short else REVIEWED_LABEL


def review_badges(standing: ReviewStanding | None) -> list[FT]:
    """The badges an entry's standing earns — none when it was never reviewed."""
    if standing is None:
        return []
    badges: list[FT] = []
    if standing["revised_after_feedback"]:
        badges.append(Badge(REVISED_AFTER_FEEDBACK_LABEL, variant=BadgeT.success, size=Size.sm))
    if standing["reviewed_by"] is not None:
        badges.append(
            Badge(reviewed_label(standing["reviewed_by"]), variant=BadgeT.info, size=Size.sm)
        )
    return badges


__all__ = ["REVIEWED_LABEL", "REVISED_AFTER_FEEDBACK_LABEL", "review_badges", "reviewed_label"]
