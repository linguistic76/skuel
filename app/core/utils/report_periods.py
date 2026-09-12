"""Activity-report periods — one vocabulary, resolved in one place.

A report's ``time_period`` token is either a trailing window ending now
(``7d`` … ``90d``, the day counts in ``ReportTimePeriod.DAYS``) or a calendar
period addressed by its period key (``2026-W37`` — an ISO week, Monday to
Sunday; ``2026-09`` — a calendar month), whose end is fixed whether or not it
has arrived. Every consumer — the rich context builder's window, the report
generator, the admin snapshot — resolves the token here, so a token unknown to
one is unknown to all: there is no default period to fall back to.

The resolved period carries the window the RICH QUERY selects touched entities
from (``start``, no upper bound — a task completed inside the period but edited
after it must still reach the mapper) and the period's own ``end``. The DATA
cutoff the mapper counts up to is ``min(now, end)``: a September report
generated on the 11th counts nothing scheduled for the 20th, and is *partial*
until the period closes.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from core.constants import ReportTimePeriod
from core.models.enums.user_entry_enums import ReportPeriodKind
from core.utils.neo4j_temporal import convert_neo4j_datetime
from core.utils.period_keys import (
    monthly_period_key,
    monthly_period_start,
    weekly_period_key,
    weekly_period_start,
)
from core.utils.timestamp_helpers import parse_iso_utc, week_bounds


class UnknownReportPeriodError(ValueError):
    """A ``time_period`` token no report vocabulary names."""


@dataclass(frozen=True)
class ReportPeriod:
    """One report's window, resolved from its token.

    ``start`` and ``end`` are the period's first and last instants (naive local
    time, as the graph's stamps are read). For a trailing window ``end`` is the
    ``now`` it was resolved at. ``label`` names the period the way a sentence
    would ("the last 7 days", "September 2026", "week 37 of 2026").
    """

    token: str
    kind: ReportPeriodKind
    start: datetime
    end: datetime
    label: str

    @property
    def is_calendar(self) -> bool:
        return self.kind.is_calendar

    def data_cutoff(self, now: datetime) -> datetime:
        """The instant the report's counts run up to — never past the period's end."""
        return min(now, self.end)

    def is_closed(self, now: datetime) -> bool:
        """A calendar period whose end has passed; a trailing window never closes."""
        return self.is_calendar and self.end <= now

    def has_started(self, now: datetime) -> bool:
        """Whether the period has begun — a report of a period still in the
        future would count today's open work against a window that holds
        nothing yet, so nothing generates one."""
        return self.start <= now

    def is_partial_at(self, cutoff: datetime) -> bool:
        """A report counted up to ``cutoff`` is partial when the period runs past it."""
        return self.is_calendar and cutoff < self.end

    def label_through(self, cutoff: datetime) -> str:
        """The period as a sentence names it, saying so when the counts stop
        before its end: "September 2026 so far (counted through Sep 12, 2026)".
        Every reader of the label — the LLM prompt included — is told a partial
        period is partial."""
        if not self.is_partial_at(cutoff):
            return self.label
        return f"{self.label} so far (counted through {cutoff.strftime('%b %d, %Y')})"


def as_naive_utc(value: object) -> datetime | None:
    """A stored timestamp as a naive-UTC datetime, or None when absent or unreadable.

    Node properties arrive as Neo4j DateTime objects, native datetimes, or ISO
    strings (the temporal split); aware values are normalised to UTC and
    stripped, naive ones are UTC by convention (``parse_iso_utc``). One shape
    on both sides of a comparison keeps a window test TypeError-free.
    """
    moment = convert_neo4j_datetime(value)
    if moment is None and isinstance(value, str):
        moment = parse_iso_utc(value)
    if moment is None:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC).replace(tzinfo=None)
    return moment


def resolve_report_period(token: str, now: datetime) -> ReportPeriod:
    """The period a ``time_period`` token names, anchored at ``now`` for trailing windows.

    Raises:
        UnknownReportPeriodError: the token is neither a trailing window nor a
            weekly / monthly period key — no default is substituted.
    """
    days = ReportTimePeriod.DAYS.get(token)
    if days is not None:
        return ReportPeriod(
            token=token,
            kind=ReportPeriodKind.TRAILING,
            start=now - timedelta(days=days),
            end=now,
            label=f"the last {days} days",
        )
    monday = weekly_period_start(token)
    if monday is not None:
        _, sunday = week_bounds(monday)
        iso_year, iso_week, _ = monday.isocalendar()
        return ReportPeriod(
            token=token,
            kind=ReportPeriodKind.WEEK,
            start=datetime.combine(monday, time.min),
            end=datetime.combine(sunday, time.max),
            label=f"week {iso_week} of {iso_year}",
        )
    first = monthly_period_start(token)
    if first is not None:
        last = first.replace(day=monthrange(first.year, first.month)[1])
        return ReportPeriod(
            token=token,
            kind=ReportPeriodKind.MONTH,
            start=datetime.combine(first, time.min),
            end=datetime.combine(last, time.max),
            label=first.strftime("%B %Y"),
        )
    raise UnknownReportPeriodError(f"Unknown report period {token!r}")


def report_period_token(kind: str, ref_date: date) -> str:
    """The token of the calendar period of ``kind`` containing ``ref_date``.

    ``kind`` is the periodic-note vocabulary the calendar doors speak —
    ``"weekly"`` or ``"monthly"``; any other kind raises, since reports have no
    quarterly or yearly period.
    """
    if kind == "weekly":
        return weekly_period_key(ref_date)
    if kind == "monthly":
        return monthly_period_key(ref_date)
    raise UnknownReportPeriodError(f"No report period of kind {kind!r}")


__all__ = [
    "ReportPeriod",
    "UnknownReportPeriodError",
    "as_naive_utc",
    "report_period_token",
    "resolve_report_period",
]
