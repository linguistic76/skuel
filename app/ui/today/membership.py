"""Day-lens membership predicates — ONE definition of what renders where.

The Today surface renders two task surfaces:

- **Ribbon** — work-plan language: a task belongs to a day's ribbon when its
  ``scheduled_date`` OR ``due_date`` equals the viewed day (C7 widening,
  mirroring the calendar's C2 due-OR-scheduled fetch semantics).
- **Triage** — deadline language: a task is in triage when it is actually
  overdue (``due_date`` strictly before the current day). Triage renders only
  on the live current day (``build_context`` gates that); the predicate itself
  is day-agnostic so the defer guard applies it verbatim.

Both surfaces exclude the same statuses (today: exactly ``COMPLETED`` —
whether dated CANCELLED/FAILED tasks *should* render is lens-status truth,
out of C7's scope).

``TodayOrchestrator.build_context()`` (``ui/today/orchestrator.py``) renders
by these functions, and the defer guard (``adapters/inbound/today_routes.py``)
validates by the SAME function objects — guard and render share one predicate
so they cannot drift (C7, ``docs/roadmap/done/calendar-act-from-arc.md``). Never
re-implement these checks inline; import them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.enums import EntityStatus

if TYPE_CHECKING:
    from datetime import date

    from core.models.task.task import Task


# The single status-exclusion set for BOTH lens surfaces. Adding a status
# here changes what renders AND what may be deferred, in lockstep.
LENS_EXCLUDED_STATUSES: frozenset[EntityStatus] = frozenset({EntityStatus.COMPLETED})

# Field names double as ``TaskUpdateIntent`` keyword names — the defer route
# moves exactly the fields these predicates matched on.
SCHEDULED_FIELD = "scheduled_date"
DUE_FIELD = "due_date"


def status_renders_on_lens(task: Task) -> bool:
    """Whether the task's status lets it render on any lens surface."""
    return task.status not in LENS_EXCLUDED_STATUSES


def ribbon_date_fields(task: Task, view_date: date) -> tuple[str, ...]:
    """The date field(s) placing ``task`` on ``view_date``'s ribbon.

    Returns ``("scheduled_date",)``, ``("due_date",)``, both (when both equal
    ``view_date``), or ``()`` when neither matches. Status is NOT consulted —
    pair with :func:`status_renders_on_lens` (or use :func:`is_ribbon_member`).
    """
    matched: list[str] = []
    if task.scheduled_date == view_date:
        matched.append(SCHEDULED_FIELD)
    if task.due_date == view_date:
        matched.append(DUE_FIELD)
    return tuple(matched)


def is_ribbon_member(task: Task, view_date: date) -> bool:
    """Full ribbon membership: a date-field match on ``view_date`` + status."""
    return bool(ribbon_date_fields(task, view_date)) and status_renders_on_lens(task)


def is_triage_member(task: Task, today: date) -> bool:
    """Full triage membership: actually overdue (due strictly before
    ``today``) + status. ``today`` must be the real current day — triage is a
    present-tense surface (callers gate rendering to the live day)."""
    return task.due_date is not None and task.due_date < today and status_renders_on_lens(task)


__all__ = [
    "DUE_FIELD",
    "LENS_EXCLUDED_STATUSES",
    "SCHEDULED_FIELD",
    "is_ribbon_member",
    "is_triage_member",
    "ribbon_date_fields",
    "status_renders_on_lens",
]
