"""Exchange thread view — one (student, root exercise) exchange as a thread.

Renders the teacher↔student exchange chronologically: submissions (all
revisions, including entries against a RevisedExercise), feedback reports,
and revision requests, interleaved by timestamp (feedback-loop UX arc C5).
Read-only by design — each item links to its existing detail/action surface
(submitting stays at /submissions/exercise, teacher actions at
/teaching/review/{uid}); the thread adds no mutations.

Data shape: ``ExchangeThread`` rows from
``UserEntryOrchestrator.get_exchange_thread`` — entries/reports/revisions
with ISO-8601 ``created_at`` strings.
"""

from __future__ import annotations

import operator
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fasthtml.common import H3, A, Div, P, Span

from core.models.enums.pipeline import ReportSource
from core.utils.timestamp_helpers import parse_iso_utc

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.ports.query_types import (
        ExchangeThread,
        ExchangeThreadEntry,
        ExchangeThreadReport,
        ExchangeThreadRevision,
    )

from ui.enum_helpers import get_status_badge_class
from ui.feedback import Badge
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader

_EPOCH = datetime.min.replace(tzinfo=UTC)


def _sort_key(created_at: str | None) -> datetime:
    """Chronological sort key for a thread item — naive stamps are UTC
    (``parse_iso_utc``); unparseable/missing stamps sort first rather than
    dropping the item.
    """
    return parse_iso_utc(created_at) or _EPOCH


def _when(created_at: str | None) -> str:
    """Human timestamp for an item header ('' when absent/unparseable)."""
    key = _sort_key(created_at)
    if key == _EPOCH:
        return ""
    return key.strftime("%b %d, %H:%M")


def _item_card(
    *,
    kind_label: str,
    border_cls: str,
    title: str,
    created_at: str | None,
    href: str | None,
    link_label: str,
    body: FT | str = "",
    badge: FT | str = "",
) -> Div:
    """One thread item: kind + timestamp header, title, optional body + link."""
    when = _when(created_at)
    link: FT | str = ""
    if href:
        link = A(
            f"{link_label} →",
            href=href,
            cls="text-xs text-primary hover:underline mt-2 inline-block",
        )
    return Div(
        Div(
            Span(kind_label, cls="font-medium text-sm"),
            badge,
            Span(f" · {when}", cls="text-xs text-foreground/40") if when else "",
            cls="mb-1 flex items-center gap-1",
        ),
        P(title, cls="text-sm font-medium mb-0"),
        body,
        link,
        cls=f"border-l-4 {border_cls} bg-muted/50 rounded-r p-3 mb-3",
    )


def _body_block(text: str | None) -> FT | str:
    """Scrollable pre-wrapped body for report/revision content ('' when empty)."""
    if not text:
        return ""
    return Div(
        P(text, cls="text-sm whitespace-pre-wrap mb-0"),
        cls="mt-2 max-h-96 overflow-y-auto",
    )


def _entry_item(entry: ExchangeThreadEntry, viewer_is_teacher: bool) -> Div:
    """A submission in the thread, linked to the viewer's action surface."""
    revision = entry.get("revision")
    if entry.get("via_revised_uid"):
        kind = "Submission (response to revision)"
    elif revision:
        kind = f"Submission (rev {revision})"
    else:
        kind = "Submission"
    status = entry.get("status") or ""
    badge: FT | str = (
        Badge(status, variant=None, size=Size.sm, cls=get_status_badge_class(status))
        if status
        else ""
    )
    href = f"/teaching/review/{entry['uid']}" if viewer_is_teacher else f"/gradebook/{entry['uid']}"
    return _item_card(
        kind_label=kind,
        border_cls="border-l-primary",
        title=entry.get("title") or entry["uid"],
        created_at=entry.get("created_at"),
        href=href,
        link_label="Open review" if viewer_is_teacher else "Open submission",
        badge=badge,
    )


def _report_item(report: ExchangeThreadReport, viewer_is_teacher: bool) -> Div:
    """A feedback report in the thread, body falling back across both fields."""
    is_ai = report.get("processor_type") == ReportSource.LLM.value
    kind = "AI Feedback" if is_ai else "Feedback"
    # Body field splits by writer: teacher-review/AI reports fill
    # processed_content, assessments fill content — render whichever exists.
    body_text = report.get("processed_content") or report.get("content")
    if viewer_is_teacher:
        entry_uid = report.get("entry_uid")
        href = f"/teaching/review/{entry_uid}" if entry_uid else None
        link_label = "Open review"
    else:
        href = f"/entry-reports/detail?uid={report['uid']}"
        link_label = "Open feedback"
    return _item_card(
        kind_label=kind,
        border_cls="border-l-info",
        title=report.get("title") or report["uid"],
        created_at=report.get("created_at"),
        href=href,
        link_label=link_label,
        body=_body_block(body_text),
    )


def _revision_item(revision: ExchangeThreadRevision) -> Div:
    """A revision request in the thread — same detail surface for both viewers."""
    number = revision.get("revision_number")
    kind = f"Revision Request (rev {number})" if number else "Revision Request"
    return _item_card(
        kind_label=kind,
        border_cls="border-l-warning",
        title=revision.get("title") or revision["uid"],
        created_at=revision.get("created_at"),
        href=f"/revised-exercises/detail?uid={revision['uid']}",
        link_label="Open revision",
        body=_body_block(revision.get("instructions")),
    )


def render_exchange_thread(thread: ExchangeThread, viewer_uid: str) -> Div:
    """Full /exchange page content: header + the interleaved chronological thread."""
    student_uid = thread["student_uid"]
    viewer_is_teacher = viewer_uid != student_uid

    items: list[tuple[datetime, Div]] = []
    for entry in thread["entries"]:
        items.append((_sort_key(entry.get("created_at")), _entry_item(entry, viewer_is_teacher)))
    for report in thread["reports"]:
        items.append((_sort_key(report.get("created_at")), _report_item(report, viewer_is_teacher)))
    for revision in thread["revisions"]:
        items.append((_sort_key(revision.get("created_at")), _revision_item(revision)))
    items.sort(key=operator.itemgetter(0))

    student_note: FT | str = ""
    if viewer_is_teacher:
        student_note = Span(
            f"with {student_uid.removeprefix('user_')}",
            cls="text-sm text-muted-foreground",
        )

    context_line = P(
        "on ",
        A(
            thread["exercise_title"],
            href=f"/exercises/get?uid={thread['exercise_uid']}",
            cls="underline decoration-dotted hover:text-foreground",
        ),
        " ",
        student_note,
        cls="text-sm text-muted-foreground mb-6",
    )

    count = len(items)
    return Div(
        PageHeader("Exchange", subtitle=thread["exercise_title"]),
        context_line,
        H3(f"{count} item{'s' if count != 1 else ''}", cls="text-base font-semibold mb-3"),
        Div(*[card for _, card in items]),
    )


def render_exchange_not_found() -> Div:
    """The one not-found shape for /exchange — denial and absence look identical."""
    return Div(
        PageHeader("Exchange"),
        EmptyState(
            title="Exchange not found",
            description=(
                "There is no exchange to show here. It may not exist, "
                "or you may not have access to it."
            ),
        ),
    )


__all__ = ["render_exchange_thread", "render_exchange_not_found"]
