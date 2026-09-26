"""GradeBook summary — per-exercise exchange lines + conditional groups.

The one GradeBook page (feedback-loop UX arc 2 C1+C2): every exchange the
student is in as one line — exercise title, derived ``ExchangeStatus``,
latest activity, source of the latest feedback — opening its ``/exchange``
thread. Status chips and a Source select filter the lines server-side
through the ``/gradebook/lines`` HTMX fragment (the FilterBar convention:
no client-side filter logic). Below the lines, two conditional groups render
only when non-empty: Activity reports (flat) and Other feedback (received
reports outside any exchange).

Data shape: ``StudentExchangeSummaries`` rows from
``UserEntryOrchestrator.get_student_exchange_summaries``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from fasthtml.common import H2, A, Div, Form, Input, Option, P, Span
from fasthtml.common import Button as HtmlButton

from core.models.enums.pipeline import ExchangeStatus, ReportSource
from ui.components import Icon
from ui.feedback import Badge, BadgeT
from ui.forms import Select
from ui.gradebook.share_panel import PRESELECT_PARAM, PRESELECT_REVIEWERS
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.patterns.format_date import format_date

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.ports.query_types import GradebookOtherReport, StudentExchangeSummary

EXCHANGE_SECTION_ID = "gradebook-exchange"
LINES_FRAGMENT_URL = "/gradebook/lines"
# The page's name — its header, and the browser tab of every surface that
# renders under the Tasks+ sidebar with the GradeBook row lit (the page,
# the submission / report / revision detail pages). The GradeBook has no
# sidebar of its own.
GRADEBOOK_TITLE = "GradeBook"

_ALL = "all"
_VALID_STATUSES = {_ALL} | {s.value for s in ExchangeStatus}
# Source options deliberately name only the sources that exist today; the
# value set stays open — "Peer" joins as a fourth option when peer feedback
# lands (arc 2 ruling 2), with no schema or filter rework.
_SOURCE_OPTIONS: list[tuple[str, str]] = [
    ("All", _ALL),
    (ReportSource.HUMAN.get_short_label(), ReportSource.HUMAN.value),
    (ReportSource.LLM.get_short_label(), ReportSource.LLM.value),
]
_VALID_SOURCES = {value for _, value in _SOURCE_OPTIONS}


def normalize_exchange_filters(status: str, source: str) -> tuple[str, str]:
    """Clamp filter query params to known values (unknown → ``all``)."""
    return (
        status if status in _VALID_STATUSES else _ALL,
        source if source in _VALID_SOURCES else _ALL,
    )


def filter_exchange_lines(
    rows: list[StudentExchangeSummary], status: str, source: str
) -> list[StudentExchangeSummary]:
    """Apply the chip + source selection to the summary rows (server-side)."""
    out = rows
    if status != _ALL:
        out = [r for r in out if r["exchange_status"] == status]
    if source != _ALL:
        out = [r for r in out if r["latest_report_source"] == source]
    return out


def _source_label(source: str | None) -> str:
    """Short provenance label for a line ('' when the line has no feedback)."""
    if not source:
        return ""
    try:
        return ReportSource(source).get_short_label()
    except ValueError:
        return source


def _status_chip(label: str, value: str, active: bool, source: str) -> FT:
    """One status filter chip — reloads the exchange section via HTMX.

    A chip is a phone tap target: at least 36px tall, with the row's gap
    making up the 44px spacing floor between neighbours.
    """
    cls = "px-3 py-1 min-h-[36px] text-sm rounded-full border transition-colors "
    cls += (
        "bg-primary text-primary-foreground border-primary"
        if active
        else "bg-background text-foreground border-border hover:border-primary/50"
    )
    return HtmlButton(
        label,
        cls=cls,
        hx_get=f"{LINES_FRAGMENT_URL}?status={value}&source={source}",
        hx_target=f"#{EXCHANGE_SECTION_ID}",
        hx_swap="outerHTML",
    )


def _filter_bar(status: str, source: str) -> FT:
    """Status chips + Source select, both swapping the exchange section."""
    chips = [_status_chip("All", _ALL, status == _ALL, source)] + [
        _status_chip(s.get_display_name(), s.value, status == s.value, source)
        for s in ExchangeStatus
    ]
    source_form = Form(
        Span("Source", cls="text-sm text-muted-foreground"),
        Input(type="hidden", name="status", value=status),
        Select(
            *[
                Option(text, value=value, selected=source == value)
                for text, value in _SOURCE_OPTIONS
            ],
            name="source",
            # The one control on the row that is a tap target on its own: 44px.
            cls="min-h-[44px]",
        ),
        hx_get=LINES_FRAGMENT_URL,
        hx_target=f"#{EXCHANGE_SECTION_ID}",
        hx_swap="outerHTML",
        hx_trigger="change",
        cls="flex items-center gap-2 ml-auto",
    )
    return Div(
        Div(*chips, cls="flex gap-2 flex-wrap"),
        source_form,
        cls="flex flex-wrap items-center gap-3 mb-4",
    )


EXERCISE_REMOVED_LABEL = "Exercise removed"
SHARE_REVISED_NUDGE_LABEL = "Share your revised work"
"""The nudge (ADR-088 §1, R2): the encouraged route submit → feedback → revise → share, offered, never enforced."""


def share_revised_nudge_href(entry_uid: str) -> str:
    """The nudge's target: the entry's page with the Share panel open and the reviewers' groups preselected."""
    query = urlencode({"share": "1", PRESELECT_PARAM: PRESELECT_REVIEWERS})
    return f"/gradebook/{entry_uid}?{query}"


def _share_revised_nudge(row: StudentExchangeSummary) -> FT | str:
    """The "Share your revised work" line under an exchange whose latest entry is an unshared post-feedback revision."""
    if not row["latest_entry_revised_after_feedback"] or row["latest_entry_shared"]:
        return ""
    return A(
        Icon("share-2", cls="size-3.5", aria_hidden="true"),
        Span(SHARE_REVISED_NUDGE_LABEL, cls="ml-1"),
        Span(" →", aria_hidden="true"),
        href=share_revised_nudge_href(row["latest_entry_uid"]),
        cls="inline-flex items-center min-h-[36px] px-3 -mt-1 mb-2 text-xs text-primary no-underline hover:underline",
    )


def _exchange_line(row: StudentExchangeSummary) -> FT:
    """One exercise line — the whole row opens the exchange thread.

    An exchange whose exercise has been deleted keeps its line, titled from
    the turn-in snapshot and badged "Exercise removed" (Submit & Share arc
    R12) — the thread still opens. A line whose latest entry is a
    post-feedback revision not yet shared carries the "Share your revised
    work" nudge beneath it (R2) — a sibling link, never nested in the row's.
    """
    status = ExchangeStatus(row["exchange_status"])
    removed_badge: FT | str = (
        Badge(EXERCISE_REMOVED_LABEL, variant=BadgeT.outline, size=Size.sm)
        if row["exercise_removed"]
        else ""
    )
    when = format_date(row["latest_activity_at"])
    source_label = _source_label(row["latest_report_source"])
    entry_count = row["entry_count"]
    report_count = row["report_count"]
    counts = (
        f"{entry_count} submission{'s' if entry_count != 1 else ''}"
        f" · {report_count} report{'s' if report_count != 1 else ''}"
    )
    meta_parts = [part for part in (when, source_label and f"from {source_label}", counts) if part]
    line = A(
        Div(
            Div(
                P(row["exercise_title"], cls="font-semibold mb-0 text-sm"),
                P(" · ".join(meta_parts), cls="text-xs text-muted-foreground mb-0"),
                cls="flex-1 min-w-0",
            ),
            removed_badge,
            Badge(
                status.get_display_name(),
                variant=None,
                size=Size.sm,
                cls=status.get_badge_class(),
            ),
            cls="flex items-center gap-3 p-3 border border-border rounded-lg bg-background hover:border-primary/50 transition-colors",
        ),
        href=f"/exchange?exercise={row['exercise_uid']}",
        cls="block no-underline text-foreground mb-2",
    )
    return Div(line, _share_revised_nudge(row))


def render_exchange_section(rows: list[StudentExchangeSummary], status: str, source: str) -> FT:
    """The filterable exchange-lines block — the ``/gradebook/lines`` swap target.

    ``rows`` is the UNFILTERED summary list; the chip/source selection is
    applied here so the fragment re-renders chips, select, and lines as one
    consistent unit.
    """
    visible = filter_exchange_lines(rows, status, source)
    if not rows:
        body: FT = EmptyState(
            title="No exercise exchanges yet",
            description="Submit an exercise and the feedback exchange will appear here.",
            action_text="Submit work",
            action_href="/submit",
        )
    elif not visible:
        body = P(
            "No exchanges match this filter.",
            cls="text-sm text-muted-foreground py-4 text-center",
        )
    else:
        body = Div(*[_exchange_line(row) for row in visible])
    return Div(
        _filter_bar(status, source),
        body,
        id=EXCHANGE_SECTION_ID,
    )


def _other_feedback_card(row: GradebookOtherReport) -> FT:
    """One received report outside any exchange, linking to its detail page."""
    when = format_date(row["created_at"])
    source_label = _source_label(row["source"])
    meta = " · ".join(part for part in (when, source_label) if part)
    return A(
        Div(
            P(row["title"] or row["uid"], cls="font-semibold mb-0 text-sm"),
            P(meta, cls="text-xs text-muted-foreground mb-0") if meta else None,
            cls="p-3 border border-border rounded-lg bg-background hover:border-primary/50 transition-colors",
        ),
        href=f"/entry-reports/detail?uid={row['uid']}",
        cls="block no-underline text-foreground mb-2",
    )


# R13 (Submit & Share arc): the group holds feedback on entries that are not
# turn-ins — an exchange whose exercise was deleted is NOT here, it keeps its
# line above.
OTHER_FEEDBACK_SUBTITLE = "Feedback on work that isn't tied to an exercise."


def render_other_feedback_group(rows: list[GradebookOtherReport]) -> FT | None:
    """Conditional "Other feedback" group — ``None`` (hidden) when empty."""
    if not rows:
        return None
    return Div(
        H2("Other feedback", cls="text-lg font-semibold mb-1"),
        P(
            OTHER_FEEDBACK_SUBTITLE,
            cls="text-sm text-muted-foreground mb-3",
        ),
        *[_other_feedback_card(row) for row in rows],
        cls="mt-8",
    )


def render_activity_reports_group(reports_list: FT | None) -> FT | None:
    """Conditional "Activity reports" group wrapper — ``None`` (hidden) when empty.

    ``reports_list`` is the already-rendered flat list
    (``render_activity_report_list``) or ``None`` when there are no reports.
    """
    if reports_list is None:
        return None
    return Div(
        H2("Activity reports", cls="text-lg font-semibold mb-1"),
        P(
            "Holistic reports across your activity patterns.",
            cls="text-sm text-muted-foreground mb-3",
        ),
        reports_list,
        cls="mt-8",
    )


__all__ = [
    "EXCHANGE_SECTION_ID",
    "GRADEBOOK_TITLE",
    "LINES_FRAGMENT_URL",
    "SHARE_REVISED_NUDGE_LABEL",
    "filter_exchange_lines",
    "normalize_exchange_filters",
    "render_activity_reports_group",
    "render_exchange_section",
    "render_other_feedback_group",
    "share_revised_nudge_href",
]
