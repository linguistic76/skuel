"""The creation rule: a task created without a date is due the day it is created.

``Task.with_creation_due_date`` is the one statement of the rule; the service
create primitive and the template spawn apply it (their reach is pinned in
``tests/unit/test_tasks_core_service.py`` and
``tests/unit/services/ps_engagement/test_spawn_builders.py``). What is pinned
here is the rule itself — which tasks it touches, what day it picks, and that
it is a pure ``replace`` (the input is never mutated, everything else survives).

The day lens (``ui/today/membership.py``) renders a task by ``due_date`` OR
``scheduled_date`` — the rule exists so that "neither" is not a state a created
task can be in, and the last test closes that loop against the real predicate.
"""

from __future__ import annotations

from datetime import date, datetime

from core.models.enums import EntityStatus
from core.models.task.task import Task
from ui.today.membership import is_ribbon_member, is_triage_member

CREATED_AT = datetime(2026, 9, 9, 19, 2, 55)
CREATED_DAY = CREATED_AT.date()


def _task(**overrides: object) -> Task:
    fields: dict[str, object] = {
        "uid": "task_rule_fixture",
        "title": "Pay monthly bills",
        "user_uid": "user_test",
        "created_at": CREATED_AT,
    }
    fields.update(overrides)
    return Task(**fields)  # type: ignore[arg-type]


def test_undated_task_is_due_on_its_creation_day() -> None:
    """The day is the entity's own ``created_at`` stamp, not the clock: the
    fixture's historical stamp is what comes back, never ``date.today()``."""
    dated = _task().with_creation_due_date()
    assert dated.due_date == CREATED_DAY
    assert dated.scheduled_date is None, "the rule speaks deadline language only"


def test_a_due_date_is_left_alone() -> None:
    task = _task(due_date=date(2026, 9, 30))
    assert task.with_creation_due_date() is task


def test_a_work_date_without_a_deadline_is_a_date() -> None:
    """Quick-add creates ``scheduled_date`` only ("I'll work on it that day") —
    the rule must not turn that into a same-day deadline."""
    task = _task(scheduled_date=date(2026, 9, 20))
    assert task.with_creation_due_date() is task
    assert task.due_date is None


def test_born_completed_earlier_takes_the_completion_day() -> None:
    """A historical ``✅`` line ingested later was lived on the day it was done."""
    done = date(2026, 7, 1)
    dated = _task(status=EntityStatus.COMPLETED, completion_date=done).with_creation_due_date()
    assert dated.due_date == done


def test_born_completed_on_the_creation_day_keeps_the_creation_day() -> None:
    """Completion on or after creation is not "earlier": the deadline stays the
    creation day (the request door defaults a dateless COMPLETED create to
    today, which is this branch on a live create)."""
    dated = _task(
        status=EntityStatus.COMPLETED, completion_date=CREATED_DAY
    ).with_creation_due_date()
    assert dated.due_date == CREATED_DAY


def test_rule_is_a_pure_replace() -> None:
    original = _task(tags=("bills",), priority=None)
    dated = original.with_creation_due_date()
    assert original.due_date is None, "frozen input mutated"
    assert dated is not original
    assert (dated.uid, dated.title, dated.user_uid, dated.tags, dated.created_at) == (
        original.uid,
        original.title,
        original.user_uid,
        original.tags,
        original.created_at,
    )


def test_a_dated_task_renders_on_the_day_lens() -> None:
    """The loop the rule closes: an undated task matched no day's ribbon and no
    triage; the dated one is on its creation day's ribbon and in triage the
    day after."""
    undated = _task()
    assert not is_ribbon_member(undated, CREATED_DAY)
    assert not is_triage_member(undated, date(2026, 9, 10))

    dated = undated.with_creation_due_date()
    assert is_ribbon_member(dated, CREATED_DAY)
    assert is_triage_member(dated, date(2026, 9, 10))
