"""
Knowledge Notes Surface (Entry-Enrichment PR 4)
================================================

Renders the ``/submissions/knowledge`` list: every ``pipeline: knowledge``
entry with its grounded-Ku chips. Grounding edges are eager writes — the
user is editor, not approver (ruling 2026-07-11) — so each chip carries a
one-click × that calls the grounding remove route and drops the chip in
place. Removals are permanent: the pair is never re-inferred, and each
removal is logged as threshold-calibration data.

Chip anatomy: Ku title links to the reading page (``/explore/ku/{uid}``);
inferred chips show the edge confidence as a percentage; explicit chips
(EXTRACT_ACTIVITIES ``@ku()`` refs — no ``confidence`` property) show none.
The × posts to ``POST /api/user-entries/grounding/remove`` with
``hx-swap="none"`` — success removes the chip client-side, failure surfaces
through the global X-Toast listener.
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import A, Button, Div, P, Span

from ui.components import Card, Icon
from ui.learning_loop.report import format_date
from ui.patterns.empty_state import EmptyState


def _grounding_chip(entry_uid: str, chip: dict[str, Any]) -> Any:
    """One removable grounded-Ku chip."""
    ku_uid = str(chip.get("ku_uid") or "")
    ku_title = str(chip.get("ku_title") or ku_uid)
    confidence = chip.get("confidence")

    confidence_label: Any = None
    if isinstance(confidence, (int, float)):
        confidence_label = Span(
            f"{round(float(confidence) * 100)}%",
            cls="text-[11px] text-muted-foreground",
        )

    return Span(
        A(
            ku_title,
            href=f"/explore/ku/{ku_uid}",
            cls="hover:underline",
        ),
        confidence_label,
        Button(
            Icon("x", size=12),
            type="button",
            hx_post=f"/api/user-entries/grounding/remove?uid={entry_uid}&ku_uid={ku_uid}",
            hx_swap="none",
            hx_confirm=(f'Remove "{ku_title}" from this note? The link will not be re-inferred.'),
            hx_disabled_elt="this",
            hx_on__after_request=(
                "if(event.detail.successful) this.closest('[data-grounding-chip]').remove()"
            ),
            cls=(
                "inline-flex items-center justify-center w-4 h-4 rounded-full "
                "text-muted-foreground hover:text-foreground hover:bg-accent"
            ),
            aria_label=f"Remove grounded concept {ku_title}",
        ),
        data_grounding_chip="1",
        cls=(
            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border "
            "border-border bg-muted/40 text-[13px] font-medium text-foreground"
        ),
    )


def _entry_row(row: dict[str, Any]) -> Any:
    """One knowledge entry: title, date, and its grounded-Ku chips."""
    uid = str(row.get("uid") or "")
    title = str(row.get("title") or "Untitled")
    created_str = format_date(row.get("created_at"))
    chips = [c for c in (row.get("grounded_kus") or []) if c.get("ku_uid")]

    chips_section: Any
    if chips:
        chips_section = Div(
            *[_grounding_chip(uid, c) for c in chips],
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
        cls="bg-background shadow-sm mb-2",
        id=f"knowledge-entry-{uid}",
    )


def render_knowledge_notes_list(rows: list[dict[str, Any]]) -> Any:
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
    return Div(*[_entry_row(r) for r in rows])


__all__ = ["render_knowledge_notes_list"]
