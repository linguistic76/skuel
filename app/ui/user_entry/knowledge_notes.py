"""
Knowledge Chips
===============

An entry's knowledge links (``APPLIES_KNOWLEDGE`` to a published Ku or
PathStep), shown as chips. Three pages render the same chip, each to the
entry's owner only:

- ``/submissions/knowledge`` — every ``pipeline: knowledge`` entry with its
  chips (``render_knowledge_notes_list``);
- ``/journals/{uid}`` — a periodic note on a grounded pipeline
  (``Pipeline.grounds_knowledge``), its chips under the editor
  (``EntryKnowledgeChips``);
- ``/gradebook/{uid}`` — the owner's page for any entry on a grounded
  pipeline, its chips under the submission card (``EntryKnowledgeChips``). A
  recipient's card never shows them.

Chip anatomy: the title links to the reading page (``/explore/ku/{uid}`` or
``/explore/ps/{uid}``). A chip the grounding pass inferred shows the edge
confidence as a percentage and carries a one-click × — grounding edges are
eager writes, the user is editor, not approver — which posts to
``POST /api/user-entries/grounding/remove`` with ``hx-swap="none"``: success
removes the chip client-side, failure surfaces through the global X-Toast
listener. Removals are permanent: the pair is never re-inferred, and each is
logged as threshold-calibration data. A chip the owner named with ``@ku`` has
no confidence and no ×: the text is where they unname it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Button, Div, P, Span

from core.models.enums.entity_enums import EntityType
from ui.components import Card, Icon
from ui.learning_loop.report import format_date
from ui.patterns.empty_state import EmptyState

if TYPE_CHECKING:
    from core.ports.query_types import KnowledgeChip, KnowledgeEntryGroundingRow

# The reading page a chip opens, by the kind of knowledge it links.
_READING_PAGE = {
    EntityType.KU: "/explore/ku/",
    EntityType.PATH_STEP: "/explore/ps/",
}


def KnowledgeLinkChip(entry_uid: str, chip: KnowledgeChip) -> Any:
    """One knowledge-link chip; removable only when the grounding pass inferred it."""
    uid = chip["uid"]
    title = chip["title"] or uid
    confidence = chip["confidence"]

    confidence_label: Any = None
    if confidence is not None:
        confidence_label = Span(
            f"{round(confidence * 100)}%",
            cls="text-11 text-muted-foreground",
        )

    remove_button: Any = None
    if chip["inferred"]:
        remove_button = Button(
            Icon("x", size=12),
            type="button",
            hx_post=f"/api/user-entries/grounding/remove?uid={entry_uid}&ku_uid={uid}",
            hx_swap="none",
            hx_confirm=(f'Remove "{title}" from this note? The link will not be re-inferred.'),
            hx_disabled_elt="this",
            hx_on__after_request=(
                "if(event.detail.successful) this.closest('[data-grounding-chip]').remove()"
            ),
            cls=(
                "inline-flex items-center justify-center w-4 h-4 rounded-full "
                "text-muted-foreground hover:text-foreground hover:bg-accent"
            ),
            aria_label=f"Remove grounded concept {title}",
        )

    reading_page = _READING_PAGE.get(chip["entity_type"])
    return Span(
        A(title, href=f"{reading_page}{uid}", cls="hover:underline")
        if reading_page
        else Span(title),
        confidence_label,
        remove_button,
        data_grounding_chip="1",
        cls=(
            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border "
            "border-border bg-muted/40 text-13 font-medium text-foreground"
        ),
    )


def EntryKnowledgeChips(
    entry_uid: str,
    chips: list[KnowledgeChip] | None,
    cls: str = "max-w-[760px] mx-auto w-full mt-6",
) -> Any:
    """The knowledge an entry is linked to, as a titled row of chips.

    ``chips`` is None when the read failed — said as such, never shown as an
    entry linked to nothing. An entry with no links renders nothing. ``cls``
    places the section on its page; the default sits it under the periodic
    note's editor column.
    """
    if chips is None:
        body: Any = P(
            "Could not load this note's knowledge links.",
            cls="text-xs text-destructive mb-0",
        )
    elif not chips:
        return None
    else:
        body = Div(
            *[KnowledgeLinkChip(entry_uid, c) for c in chips],
            cls="flex flex-wrap gap-2",
        )
    return Div(
        P("Knowledge in this note", cls="text-sm font-semibold text-foreground mb-2"),
        body,
        id="entry-knowledge-chips",
        cls=cls,
    )


def _entry_row(row: KnowledgeEntryGroundingRow) -> Any:
    """One knowledge entry: title, date, and its knowledge chips."""
    uid = row["uid"]
    title = row["title"] or "Untitled"
    created_str = format_date(row["created_at"])
    chips = row["chips"]

    chips_section: Any
    if chips:
        chips_section = Div(
            *[KnowledgeLinkChip(uid, c) for c in chips],
            cls="flex flex-wrap gap-2 mt-2",
        )
    else:
        chips_section = P(
            "No grounded concepts yet.",
            cls="text-xs text-muted-foreground mt-2 mb-0",
        )

    return Card(
        Div(
            Div(
                A(title, href=f"/gradebook/{uid}", cls="font-semibold hover:underline"),
                Span(created_str, cls="text-xs text-muted-foreground ml-3"),
            ),
            chips_section,
        ),
        cls="bg-background shadow-xs p-4",
        id=f"knowledge-entry-{uid}",
    )


def render_knowledge_notes_list(rows: list[KnowledgeEntryGroundingRow]) -> Any:
    """The full knowledge-notes list, newest first."""
    if not rows:
        return EmptyState(
            title="No knowledge notes yet",
            description=(
                "Sync vault notes carrying `pipeline: knowledge` frontmatter "
                "to teach SKUEL about you — they will appear here with the "
                "concepts they ground to."
            ),
        )
    return Div(*[_entry_row(r) for r in rows], cls="space-y-2")


__all__ = ["EntryKnowledgeChips", "KnowledgeLinkChip", "render_knowledge_notes_list"]
