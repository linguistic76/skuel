"""What a period's report may count and list — one predicate set, two consumers.

The rich context hands both the report generator's mapper and the admin
snapshot the CURRENT inventory (open tasks, active goals, alive habits,
pending choices, every principle) plus what was touched since the period's
start — with no upper bound, because the mapper's own stamps are the bound.
A report of a closed period must therefore decide, per row, whether the
entity belongs to that period at all: created no later than its end, a task
completed inside it or open at its end, an event dated inside it. Those
verdicts live here so the generator and the snapshot cannot drift apart.

Stamps arrive as Neo4j DateTime objects, native datetimes, ISO strings or
bare dates (the temporal split); every comparison runs on naive UTC.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.models.enums import EntityStatus
from core.utils.report_periods import as_naive_utc
from core.utils.timestamp_helpers import parse_date_value


def is_terminal_status(raw: object) -> bool:
    """Whether a stored status string names a terminal state; unreadable reads as open."""
    try:
        return EntityStatus(str(raw)).is_terminal()
    except ValueError:
        return False


def moment_of(stamp: object) -> datetime | None:
    """A stored stamp as a naive-UTC instant — a bare date is its first instant."""
    moment = as_naive_utc(stamp)
    if moment is None:
        day = parse_date_value(stamp)
        if day is None:
            return None
        moment = datetime.combine(day, datetime.min.time())
    return moment


@dataclass(frozen=True)
class PeriodEligibility:
    """The period's bounds, and what they admit.

    ``window_start`` / ``window_end`` bound the counts (the data cutoff is the
    end); ``period_end`` is the period's own end, which is later than the
    cutoff exactly when the report is partial. All naive UTC, ``None`` = open.
    """

    window_start: datetime | None
    window_end: datetime | None
    period_end: datetime | None

    @classmethod
    def for_window(
        cls, window_start: datetime, window_end: datetime, period_end: datetime | None = None
    ) -> PeriodEligibility:
        """Bounds from the report's window; ``period_end`` defaults to the window's end."""
        ceiling = as_naive_utc(window_end)
        return cls(
            window_start=as_naive_utc(window_start),
            window_end=ceiling,
            period_end=as_naive_utc(period_end) if period_end is not None else ceiling,
        )

    def in_period(self, stamp: object) -> bool:
        """Whether a stamp falls inside [window_start, window_end]; no stamp, no."""
        moment = moment_of(stamp)
        if moment is None:
            return False
        return (self.window_start is None or moment >= self.window_start) and (
            self.window_end is None or moment <= self.window_end
        )

    def existed_by_end(self, entity: Mapping[str, Any]) -> bool:  # boundary: node properties
        """Created no later than the period's end — the inventory a closed
        period's report may list at all. No ``created_at`` reads as existed."""
        created = moment_of(entity.get("created_at"))
        return not (
            created is not None and self.period_end is not None and created > self.period_end
        )

    def open_at_end(self, entity: Mapping[str, Any]) -> bool:  # boundary: node properties
        """Open at the period's end, as far as the node's stamps can tell: existed
        by then and either non-terminal now, or terminal with its terminal stamp
        (``completion_date``, else ``updated_at``) after the end. A task closed
        before the period and merely edited after it reads as open — the named
        approximation a report's metadata records."""
        if not self.existed_by_end(entity):
            return False
        if not is_terminal_status(entity.get("status")):
            return True
        closed_at = moment_of(entity.get("completion_date")) or moment_of(entity.get("updated_at"))
        return closed_at is not None and self.period_end is not None and closed_at > self.period_end

    def completed_in_period(self, entity: Mapping[str, Any]) -> bool:  # boundary: node properties
        """A task completed inside the period: status completed and its
        ``completion_date`` in the window (a completion re-edited later is not)."""
        return entity.get("status") == EntityStatus.COMPLETED and self.in_period(
            entity.get("completion_date")
        )

    def task_in_play(self, entity: Mapping[str, Any]) -> bool:  # boundary: node properties
        """The period's task denominator: completed in it, or open at its end."""
        return self.completed_in_period(entity) or self.open_at_end(entity)

    def event_in_window(self, entity: Mapping[str, Any]) -> bool:  # boundary: node properties
        """An event dated inside the window — the rich query selects every event
        from the start on, so a scheduled future event must not read as attended.
        An undated event is kept."""
        event_day = parse_date_value(entity.get("event_date"))
        if event_day is None:
            return True
        if self.window_start is not None and event_day < self.window_start.date():
            return False
        return not (self.window_end is not None and event_day > self.window_end.date())


__all__ = ["PeriodEligibility", "is_terminal_status", "moment_of"]
