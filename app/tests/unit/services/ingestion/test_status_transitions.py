"""
The vault door's ADR-087 status contract — classification + event shape (arc PR-3).
===================================================================================

The bulk upsert ``MERGE``s instead of going through
``update_with_status_guard``, so the primitive's prior-dependent jobs are
reassembled from the prior status the upsert returns. These tests pin the
derivation itself; ``tests/integration/test_vault_door_status_transitions.py``
drives it through the real ingestion doors against a real graph.

The derivation is two steps, and the split is the point: classification says
WHICH entities transitioned, and the event is built from the entity as
PERSISTED — the upsert merges, so the file payload is only the half the file
happens to declare.

Pinned here:

- a file that arrives ``completed`` over a node that was not is a transition; a
  repeat (prior already ``completed``) is not — the ``--force`` guarantee;
- the mirror: prior ``completed``, new status not, clears the stamp — including a
  present-but-null status, which ERASES the stored one, and excluding an absent
  status key, which writes nothing;
- the clear is decided from the status the entity ENDS UP holding, so a file
  authored open beside a ``completion_date:`` line loses that stamp on its FIRST
  ingest, where there is no prior and therefore no transition to read;
- an entity with no stamp to lose is never listed, so an ordinary sync carries
  nothing to a write that could only no-op;
- ``occurred_at`` carries the entity's own authored completion stamp, so a
  historical vault line reports the day it happened;
- Habit and Choice get the stamp-clear and no event (``HabitCompleted`` is a
  daily occurrence, ``ChoiceMade`` is the decide moment — neither is the entity
  retiring);
- domains with no completion field (Principle, Ku) derive nothing at all.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from core.events import CalendarEventCompleted, GoalAchieved, TaskCompleted
from core.models.enums.entity_enums import EntityType
from core.services.completion_stamp import COMPLETION_FIELDS
from core.services.ingestion.status_transitions import (
    EVENT_SOURCE_FIELDS,
    build_completion_events,
    classify_ingest_status_transitions,
)

OWNER = "user_status_transitions"


def _task(uid: str, status: str, **extra: Any) -> dict[str, Any]:
    return {"uid": uid, "user_uid": OWNER, "title": uid, "status": status, **extra}


def _one_event(entity_type: EntityType, uid: str, **persisted: Any) -> Any:
    """Build the single event for ``uid`` from its persisted properties."""
    events = build_completion_events(entity_type, (uid,), {uid: {"user_uid": OWNER, **persisted}})
    assert len(events) == 1
    return events[0]


# ---------------------------------------------------------------------------
# the transition gate
# ---------------------------------------------------------------------------


def test_completed_over_absent_prior_is_a_transition() -> None:
    """A node this write created has no prior status — a create is a transition."""
    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [_task("task.born", "completed")], {}
    )

    assert transitions.completed_uids == ("task.born",)
    assert transitions.stamp_clear_uids == ()


def test_completed_over_open_prior_is_a_transition() -> None:
    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [_task("task.edited", "completed")], {"task.edited": "in_progress"}
    )

    assert transitions.completed_uids == ("task.edited",)


def test_completed_over_completed_prior_is_silent() -> None:
    """The ``--force`` guarantee: re-ingesting a completed file announces nothing."""
    entities = [_task(f"task.force-{i}", "completed") for i in range(5)]
    prior = {e["uid"]: "completed" for e in entities}

    transitions = classify_ingest_status_transitions(EntityType.TASK, entities, prior)

    assert transitions.completed_uids == ()
    assert transitions.stamp_clear_uids == ()


def test_open_over_open_prior_is_silent() -> None:
    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [_task("task.open", "in_progress")], {"task.open": "in_progress"}
    )

    assert transitions == classify_ingest_status_transitions(EntityType.TASK, [], {})


# ---------------------------------------------------------------------------
# the reopen mirror — presence, not truthiness
# ---------------------------------------------------------------------------


def test_reopen_yields_a_clear_and_no_completion() -> None:
    transitions = classify_ingest_status_transitions(
        EntityType.TASK,
        [_task("task.reopened", "in_progress", completion_date="2026-03-04")],
        {"task.reopened": "completed"},
    )

    assert transitions.stamp_clear_uids == ("task.reopened",)
    assert transitions.completed_uids == ()


def test_missing_status_key_is_not_a_reopen() -> None:
    """No ``status`` key writes no status — the stored ``completed`` survives."""
    entity = {"uid": "task.no-status", "user_uid": OWNER, "title": "No status"}

    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [entity], {"task.no-status": "completed"}
    )

    assert transitions.stamp_clear_uids == ()
    assert transitions.completed_uids == ()


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

    assert transitions.stamp_clear_uids == ("task.erased",)
    assert transitions.completed_uids == ()


def test_a_null_status_over_an_open_prior_changes_nothing() -> None:
    entity = {"uid": "task.erased-open", "user_uid": OWNER, "status": None}

    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [entity], {"task.erased-open": "in_progress"}
    )

    assert transitions.stamp_clear_uids == ()
    assert transitions.completed_uids == ()


# ---------------------------------------------------------------------------
# the stamp-clear reaches a create, where there is no transition to read
# ---------------------------------------------------------------------------


def test_a_new_file_authored_open_with_a_stamp_is_cleared() -> None:
    """The half the guard cannot judge, on the door that can.

    A brand-new file carrying ``status: in_progress`` beside a leftover
    ``completion_date:`` has NO prior status, so no transition exists to be read
    — and the stamp lands on an entity that is open. The clear is decided from
    the status the entity ends up holding, which is knowable for a create.
    """
    transitions = classify_ingest_status_transitions(
        EntityType.TASK,
        [_task("task.born-open", "in_progress", completion_date="2026-03-04")],
        {},
    )

    assert transitions.stamp_clear_uids == ("task.born-open",)
    assert transitions.completed_uids == ()


def test_a_new_file_authored_open_without_a_stamp_is_silent() -> None:
    """Nothing to clear, so nothing is carried to the write."""
    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [_task("task.born-clean", "in_progress")], {}
    )

    assert transitions.stamp_clear_uids == ()


def test_re_ingesting_the_same_open_file_clears_again() -> None:
    """``SET n += props`` re-writes the stamp on every ingest, so the clear
    cannot be a one-time repair of the first one."""
    transitions = classify_ingest_status_transitions(
        EntityType.TASK,
        [_task("task.still-open", "in_progress", completion_date="2026-03-04")],
        {"task.still-open": "active"},
    )

    assert transitions.stamp_clear_uids == ("task.still-open",)


def test_a_stamp_authored_beside_completed_is_kept() -> None:
    """The file is the source of truth for its own dates — this one is honest."""
    transitions = classify_ingest_status_transitions(
        EntityType.TASK,
        [_task("task.honest", "completed", completion_date="2026-03-04")],
        {},
    )

    assert transitions.completed_uids == ("task.honest",)
    assert transitions.stamp_clear_uids == ()


def test_a_completed_node_correcting_its_date_keeps_the_stamp() -> None:
    """No ``status`` key resolves against the prior, which is ``completed`` — so
    a file that edits only its ``completion_date:`` re-dates rather than strands."""
    entity = {"uid": "task.re-dated", "user_uid": OWNER, "completion_date": "2026-03-05"}

    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [entity], {"task.re-dated": "completed"}
    )

    assert transitions.stamp_clear_uids == ()
    assert transitions.completed_uids == ()


def test_an_open_node_gaining_a_bare_stamp_is_cleared() -> None:
    """The same no-status shape over an OPEN prior is the stranding one."""
    entity = {"uid": "task.bare-stamp", "user_uid": OWNER, "completion_date": "2026-03-05"}

    transitions = classify_ingest_status_transitions(
        EntityType.TASK, [entity], {"task.bare-stamp": "active"}
    )

    assert transitions.stamp_clear_uids == ("task.bare-stamp",)


def test_each_domain_reads_its_own_stamp_field() -> None:
    """The field is per-domain (``COMPLETION_FIELDS``), so a Task's key must not
    be what decides a Habit — the datetime domains stamp ``completed_at``."""
    for entity_type, field in COMPLETION_FIELDS.items():
        uid = f"{entity_type.value}.open-stamped"
        transitions = classify_ingest_status_transitions(
            entity_type,
            [{"uid": uid, "user_uid": OWNER, "status": "active", field: "2026-03-04"}],
            {},
        )
        assert transitions.stamp_clear_uids == (uid,), entity_type

        wrong_field = classify_ingest_status_transitions(
            entity_type,
            [{"uid": uid, "user_uid": OWNER, "status": "active", "updated_at": "2026-03-04"}],
            {},
        )
        assert wrong_field.stamp_clear_uids == (), entity_type


# ---------------------------------------------------------------------------
# events are built from PERSISTED state
# ---------------------------------------------------------------------------


def test_the_event_reads_persisted_properties_the_file_never_declared() -> None:
    """The upsert merges, so the node keeps what the file omits (Codex #1290).

    A file that changes nothing but ``status`` still leaves the stored due date
    and elapsed duration on the node; an event built from the file payload would
    report the task as neither overdue nor timed.
    """
    event = _one_event(
        EntityType.TASK,
        "task.merged",
        completion_date=date(2026, 3, 14),
        due_date=date(2026, 3, 10),
        actual_minutes=45,
    )

    assert isinstance(event, TaskCompleted)
    assert event.was_overdue is True
    assert event.completion_time_seconds == 45 * 60


def test_a_uid_with_no_persisted_row_is_skipped() -> None:
    """A node that vanished between the write and the read has nobody to serve."""
    assert build_completion_events(EntityType.TASK, ("task.gone",), {}) == ()


def test_event_source_fields_cover_every_property_the_events_read() -> None:
    """The fetched field list is the contract — a field added to an event
    without being listed here reads as absent forever."""
    assert set(EVENT_SOURCE_FIELDS) == {EntityType.TASK, EntityType.GOAL, EntityType.EVENT}
    for fields in EVENT_SOURCE_FIELDS.values():
        assert "user_uid" in fields


# ---------------------------------------------------------------------------
# occurred_at carries the authored stamp
# ---------------------------------------------------------------------------


def test_task_occurred_at_is_the_authored_completion_date() -> None:
    event = _one_event(EntityType.TASK, "task.historic", completion_date=date(2026, 3, 4))

    assert event.occurred_at == datetime(2026, 3, 4, 0, 0)


def test_task_occurred_at_accepts_an_iso_string_stamp() -> None:
    """Dates reach the graph as native values or strings depending on the writer."""
    event = _one_event(EntityType.TASK, "task.iso", completion_date="2026-03-04")

    assert event.occurred_at == datetime(2026, 3, 4, 0, 0)


def test_task_overdue_is_measured_against_the_completion_moment() -> None:
    """A task completed on time in March is not overdue because March has passed."""
    on_time = _one_event(
        EntityType.TASK, "task.ontime", completion_date="2026-03-04", due_date="2026-03-10"
    )
    late = _one_event(
        EntityType.TASK, "task.late", completion_date="2026-03-14", due_date="2026-03-10"
    )

    assert on_time.was_overdue is False
    assert late.was_overdue is True


def test_task_unreadable_optional_field_still_completes() -> None:
    """A malformed optional analytics field must not swallow a declared completion."""
    event = _one_event(EntityType.TASK, "task.messy", actual_minutes="soon", due_date="whenever")

    assert event.completion_time_seconds is None
    assert event.was_overdue is False


# ---------------------------------------------------------------------------
# per-domain shapes
# ---------------------------------------------------------------------------


def test_goal_duration_spans_created_at_to_the_achievement() -> None:
    """Measured to the completion moment, which is what this event's occurred_at says."""
    event = _one_event(
        EntityType.GOAL,
        "goal.spanning",
        created_at="2026-01-01T00:00:00",
        achieved_date="2026-03-02",
    )

    assert isinstance(event, GoalAchieved)
    assert event.goal_uid == "goal.spanning"
    assert event.actual_duration_days == 60
    assert event.occurred_at == datetime(2026, 3, 2, 0, 0)


def test_goal_created_at_may_carry_a_utc_offset() -> None:
    """The preparer canonicalizes an authored created_at to a Z-suffixed UTC string,
    while occurred_at is naive — the subtraction has to normalize."""
    event = _one_event(
        EntityType.GOAL,
        "goal.aware",
        created_at="2026-01-01T00:00:00Z",
        achieved_date="2026-03-02",
    )

    assert event.actual_duration_days == 60


def test_goal_backdated_over_an_ingest_stamped_created_at_floors_at_zero() -> None:
    """A file authoring no created_at is stamped with the ingest moment.

    Without the floor the span would be negative, which the duration-calibration
    handler reads as "ahead of schedule".
    """
    event = _one_event(
        EntityType.GOAL,
        "goal.backdated",
        created_at="2026-09-06T12:00:00",
        achieved_date="2026-03-04",
    )

    assert event.actual_duration_days == 0


def test_goal_without_created_at_reports_no_duration() -> None:
    event = _one_event(EntityType.GOAL, "goal.undated")

    assert isinstance(event, GoalAchieved)
    assert event.actual_duration_days is None


def test_event_completion_date_falls_back_to_the_completion_moment() -> None:
    event = _one_event(EntityType.EVENT, "event.done", completed_at="2026-03-04T18:30:00")

    assert isinstance(event, CalendarEventCompleted)
    assert event.completion_date == date(2026, 3, 4)
    assert event.quality_score is None
    assert event.occurred_at == datetime(2026, 3, 4, 18, 30)


def test_event_prefers_its_authored_event_date() -> None:
    event = _one_event(
        EntityType.EVENT,
        "event.dated",
        event_date="2026-02-14",
        completed_at="2026-03-04T18:30:00",
    )

    assert event.completion_date == date(2026, 2, 14)


def test_habit_and_choice_clear_but_never_announce() -> None:
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

        # It IS a transition — it just earns a stamp, never an event.
        assert completed.completed_uids == (uid,), entity_type
        assert build_completion_events(entity_type, (uid,), {uid: {}}) == (), entity_type
        assert reopened.stamp_clear_uids == (uid,), entity_type
        assert reopened.completed_uids == (), entity_type


def test_domains_without_a_completion_field_derive_nothing() -> None:
    """Principle has no COMPLETED status; Ku has no completion field at all."""
    for entity_type in (EntityType.PRINCIPLE, EntityType.KU):
        transitions = classify_ingest_status_transitions(
            entity_type,
            [{"uid": "x", "user_uid": OWNER, "status": "completed"}],
            {"x": "active"},
        )
        assert transitions.completed_uids == (), entity_type
        assert transitions.stamp_clear_uids == (), entity_type
