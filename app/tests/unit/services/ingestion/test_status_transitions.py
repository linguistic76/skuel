"""
The vault door's ADR-087 status contract — classification (arc PR-3).
=====================================================================

The bulk upsert ``MERGE``s instead of going through
``update_with_status_guard``, so the primitive's prior-dependent jobs are
reassembled from the prior status the upsert returns. These tests pin the
derivation itself; ``tests/integration/test_vault_door_status_transitions.py``
drives it through the real ingestion doors against a real graph.

Pinned here:

- a file that arrives ``completed`` over a node that was not publishes the
  domain's completion event; a repeat (prior already ``completed``) publishes
  nothing — the ``--force`` re-ingest guarantee;
- the mirror: prior ``completed``, new status not, yields a reopen-clear and no
  event;
- ``occurred_at`` carries the entity's own authored completion stamp, so a
  historical vault line reports the day it happened;
- Habit and Choice get the reopen-clear and no event (``HabitCompleted`` is a
  daily occurrence, ``ChoiceMade`` is the decide moment — neither is the entity
  retiring);
- domains with no completion field (Principle, Ku) derive nothing at all.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from core.events import CalendarEventCompleted, GoalAchieved, TaskCompleted
from core.models.enums.entity_enums import EntityType
from core.services.ingestion.status_transitions import classify_ingest_status_transitions

OWNER = "user_status_transitions"


def _task(uid: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"uid": uid, "user_uid": OWNER, "title": uid, "status": status, **extra}


# ---------------------------------------------------------------------------
# the transition gate
# ---------------------------------------------------------------------------


def test_completed_over_absent_prior_publishes() -> None:
    """A node this write created has no prior status — a create is a transition."""
    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [_task("task.born", "completed")], {}
    )

    (event,) = transitions.completion_events
    assert isinstance(event, TaskCompleted)
    assert event.task_uid == "task.born"
    assert event.user_uid == OWNER
    assert event.is_repeat is False
    assert transitions.reopened_uids == ()


def test_completed_over_open_prior_publishes() -> None:
    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [_task("task.edited", "completed")], {"task.edited": "in_progress"}
    )

    (event,) = transitions.completion_events
    assert isinstance(event, TaskCompleted)
    assert event.task_uid == "task.edited"


def test_completed_over_completed_prior_is_silent() -> None:
    """The ``--force`` guarantee: re-ingesting a completed file publishes nothing."""
    entities = [_task(f"task.force-{i}", "completed") for i in range(5)]
    prior = {e["uid"]: "completed" for e in entities}

    transitions = classify_ingest_status_transitions(EntityType.TASK, entities, prior)

    assert transitions.completion_events == ()
    assert transitions.reopened_uids == ()


def test_open_over_open_prior_is_silent() -> None:
    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [_task("task.open", "in_progress")], {"task.open": "in_progress"}
    )

    assert transitions == classify_ingest_status_transitions(EntityType.TASK, [], {})


# ---------------------------------------------------------------------------
# the reopen mirror
# ---------------------------------------------------------------------------


def test_reopen_clears_and_publishes_nothing() -> None:
    transitions = classify_ingest_status_transitions(
        EntityType.TASK,
        [_task("task.reopened", "in_progress", completion_date="2026-03-04")],
        {"task.reopened": "completed"},
    )

    assert transitions.reopened_uids == ("task.reopened",)
    assert transitions.completion_events == ()


def test_missing_new_status_is_not_a_reopen() -> None:
    """No ``status`` key writes no status — the stored ``completed`` survives."""
    entity = {"uid": "task.no-status", "user_uid": OWNER, "title": "No status"}

    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [entity], {"task.no-status": "completed"}
    )

    assert transitions.reopened_uids == ()
    assert transitions.completion_events == ()


def test_a_present_but_null_status_is_a_reopen() -> None:
    """``status:`` / ``status: none`` prepare to a present key holding None.

    The upsert's ``SET n += props`` DELETES a property written null, so the
    entity ends up with no status at all — definitively not completed. Presence
    of the key, not truthiness of the value, is what separates this from the
    test above.
    """
    entity = {"uid": "task.erased", "user_uid": OWNER, "status": None}

    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [entity], {"task.erased": "completed"}
    )

    assert transitions.reopened_uids == ("task.erased",)
    assert transitions.completion_events == ()


def test_a_null_status_over_an_open_prior_changes_nothing() -> None:
    entity = {"uid": "task.erased-open", "user_uid": OWNER, "status": None}

    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [entity], {"task.erased-open": "in_progress"}
    )

    assert transitions.reopened_uids == ()
    assert transitions.completion_events == ()


# ---------------------------------------------------------------------------
# occurred_at carries the authored stamp
# ---------------------------------------------------------------------------


def test_task_occurred_at_is_the_authored_completion_date() -> None:
    transitions = classify_ingest_status_transitions(
        EntityType.TASK,
        [_task("task.historic", "completed", completion_date=date(2026, 3, 4))],
        {},
    )

    (event,) = transitions.completion_events
    assert event.occurred_at == datetime(2026, 3, 4, 0, 0)


def test_task_occurred_at_accepts_an_iso_string_stamp() -> None:
    """YAML hands dates through as native dates or strings depending on quoting."""
    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [_task("task.iso", "completed", completion_date="2026-03-04")], {}
    )

    (event,) = transitions.completion_events
    assert event.occurred_at == datetime(2026, 3, 4, 0, 0)


def test_task_overdue_is_measured_against_the_completion_moment() -> None:
    """A task completed on time in March is not overdue because March has passed."""
    on_time = classify_ingest_status_transitions(
        EntityType.TASK,
        [_task("task.ontime", "completed", completion_date="2026-03-04", due_date="2026-03-10")],
        {},
    )
    late = classify_ingest_status_transitions(
        EntityType.TASK,
        [_task("task.late", "completed", completion_date="2026-03-14", due_date="2026-03-10")],
        {},
    )

    (on_time_event,) = on_time.completion_events
    (late_event,) = late.completion_events
    assert isinstance(on_time_event, TaskCompleted)
    assert isinstance(late_event, TaskCompleted)
    assert on_time_event.was_overdue is False
    assert late_event.was_overdue is True


def test_task_completion_time_comes_from_actual_minutes() -> None:
    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [_task("task.timed", "completed", actual_minutes=45)], {}
    )

    (event,) = transitions.completion_events
    assert isinstance(event, TaskCompleted)
    assert event.completion_time_seconds == 45 * 60


def test_task_unreadable_optional_field_still_completes() -> None:
    """A malformed optional analytics field must not swallow a declared completion."""
    transitions = classify_ingest_status_transitions(
        EntityType.TASK,
        [_task("task.messy", "completed", actual_minutes="soon", due_date="whenever")],
        {},
    )

    (event,) = transitions.completion_events
    assert isinstance(event, TaskCompleted)
    assert event.completion_time_seconds is None
    assert event.was_overdue is False


# ---------------------------------------------------------------------------
# per-domain shapes
# ---------------------------------------------------------------------------


def test_goal_duration_spans_created_at_to_the_achievement() -> None:
    """Measured to the completion moment, which is what this event's occurred_at says."""
    entity = {
        "uid": "goal.spanning",
        "user_uid": OWNER,
        "status": "completed",
        "created_at": "2026-01-01T00:00:00",
        "achieved_date": "2026-03-02",
    }

    transitions = classify_ingest_status_transitions(EntityType.GOAL, [entity], {})

    (event,) = transitions.completion_events
    assert isinstance(event, GoalAchieved)
    assert event.goal_uid == "goal.spanning"
    assert event.actual_duration_days == 60
    assert event.occurred_at == datetime(2026, 3, 2, 0, 0)


def test_goal_backdated_over_an_ingest_stamped_created_at_floors_at_zero() -> None:
    """A file authoring no created_at is stamped with the ingest moment.

    Without the floor the span would be negative, which the duration-calibration
    handler reads as "ahead of schedule".
    """
    entity = {
        "uid": "goal.backdated",
        "user_uid": OWNER,
        "status": "completed",
        "created_at": "2026-09-06T12:00:00",
        "achieved_date": "2026-03-04",
    }

    (event,) = classify_ingest_status_transitions(EntityType.GOAL, [entity], {}).completion_events

    assert isinstance(event, GoalAchieved)
    assert event.actual_duration_days == 0


def test_goal_without_created_at_reports_no_duration() -> None:
    entity = {"uid": "goal.undated", "user_uid": OWNER, "status": "completed"}

    (event,) = classify_ingest_status_transitions(EntityType.GOAL, [entity], {}).completion_events

    assert isinstance(event, GoalAchieved)
    assert event.actual_duration_days is None


def test_event_completion_date_falls_back_to_the_completion_moment() -> None:
    entity = {
        "uid": "event.done",
        "user_uid": OWNER,
        "status": "completed",
        "completed_at": "2026-03-04T18:30:00",
    }

    (event,) = classify_ingest_status_transitions(EntityType.EVENT, [entity], {}).completion_events

    assert isinstance(event, CalendarEventCompleted)
    assert event.completion_date == date(2026, 3, 4)
    assert event.quality_score is None
    assert event.occurred_at == datetime(2026, 3, 4, 18, 30)


def test_event_prefers_its_authored_event_date() -> None:
    entity = {
        "uid": "event.dated",
        "user_uid": OWNER,
        "status": "completed",
        "event_date": "2026-02-14",
        "completed_at": "2026-03-04T18:30:00",
    }

    (event,) = classify_ingest_status_transitions(EntityType.EVENT, [entity], {}).completion_events

    assert isinstance(event, CalendarEventCompleted)
    assert event.completion_date == date(2026, 2, 14)


def test_habit_and_choice_clear_but_never_publish() -> None:
    """Neither domain has an entity-completion event; inventing one would be bloat."""
    for entity_type, uid in ((EntityType.HABIT, "habit.x"), (EntityType.CHOICE, "choice.x")):
        completed = classify_ingest_status_transitions(
            entity_type, [{"uid": uid, "user_uid": OWNER, "status": "completed"}], {}
        )
        reopened = classify_ingest_status_transitions(
            entity_type,
            [{"uid": uid, "user_uid": OWNER, "status": "active"}],
            {uid: "completed"},
        )

        assert completed.completion_events == (), entity_type
        assert completed.reopened_uids == (), entity_type
        assert reopened.reopened_uids == (uid,), entity_type
        assert reopened.completion_events == (), entity_type


def test_domains_without_a_completion_field_derive_nothing() -> None:
    """Principle has no COMPLETED status; Ku has no completion field at all."""
    for entity_type in (EntityType.PRINCIPLE, EntityType.KU):
        transitions = classify_ingest_status_transitions(
            entity_type,
            [{"uid": "x", "user_uid": OWNER, "status": "completed"}],
            {"x": "active"},
        )
        assert transitions.completion_events == (), entity_type
        assert transitions.reopened_uids == (), entity_type
