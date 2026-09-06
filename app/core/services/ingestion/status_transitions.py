"""
Ingest-door status transitions — the vault's half of ADR-087.
=============================================================

The app's update chokepoints decide a status transition *by* the write
(``backend.update_with_status_guard``): the statement takes the node's
write-lock, reads the prior status, applies the stamp or clears it, and returns
the prior so the service can derive its verdicts. The vault doors do not go
through that primitive — they ``MERGE`` in bulk — so the same three jobs are
reassembled here from the prior status the bulk upsert now returns
(``IngestionResult.prior_status_by_uid``):

1. **the completion event** on a genuine transition — prior not ``completed``,
   new status ``completed``;
2. **the reopen-clear** on the mirror — prior ``completed``, new status not;
3. nothing at all for a repeat, which is what makes a ``--force`` re-ingest of
   a vault full of already-completed files silent.

Only the five stamping domains have a completion field (``COMPLETION_FIELDS``),
and only three of them have an entity-completion event: ``HabitCompleted`` is a
logged daily *occurrence* and ``ChoiceMade`` is the DRAFT→ACTIVE *decide*
moment, neither of which is the entity retiring. Habit and Choice therefore get
the reopen-clear and no event — inventing one with no subscribers would be
staged bloat, not a fix.

Every value here arrives as parsed YAML, so dates may be native ``date``
objects, ISO strings, or absent; the coercions are deliberately total (an
unparseable value reads as absent) because a malformed optional analytics field
must not stop a completion the file plainly declares.

See: /docs/decisions/ADR-087-status-guarded-conditional-writes.md,
     /docs/roadmap/vault-task-door-no-events.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from core.events import BaseEvent, CalendarEventCompleted, GoalAchieved, TaskCompleted
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.type_hints import UserUID
from core.services.completion_stamp import COMPLETION_FIELDS, completion_moment

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["IngestStatusTransitions", "classify_ingest_status_transitions"]

_COMPLETED = EntityStatus.COMPLETED.value


@dataclass(frozen=True)
class IngestStatusTransitions:
    """What one persisted batch's status changes oblige the door to do.

    ``reopened_uids`` are the entities whose completion stamp must be removed;
    ``completion_events`` are ready to publish in order. Both are empty for a
    batch that changed no entity's completion state — the ordinary case, and the
    one a ``--force`` re-ingest must produce.
    """

    reopened_uids: tuple[str, ...] = ()
    completion_events: tuple[BaseEvent, ...] = ()


def classify_ingest_status_transitions(
    entity_type: EntityType,
    # boundary: prepared ingestion entity dicts are genuinely heterogeneous —
    # parsed YAML frontmatter plus the preparer's injected keys. This is the
    # type both doors already hand to every other post-persist step.
    entities: list[dict[str, Any]],
    prior_status_by_uid: Mapping[str, str | None],
) -> IngestStatusTransitions:
    """Derive the completion events and reopen-clears one persisted batch owes.

    Args:
        entity_type: The domain being ingested. Types with no completion field
            (everything outside the five stamping domains) yield nothing.
        entities: The dicts that were just persisted, exactly as the upsert saw
            them — ``status`` is the NEW status.
        prior_status_by_uid: What each node's status was before the write, from
            ``IngestionResult.prior_status_by_uid``. A uid absent from the map is
            treated as having no prior status (the shape a create produces), so a
            file the write created and declares completed still cascades.

    Returns:
        The batch's :class:`IngestStatusTransitions`. Never raises: an entity
        with no uid, or one whose status is unreadable, is simply not a
        transition.
    """
    if entity_type not in COMPLETION_FIELDS:
        return IngestStatusTransitions()

    reopened: list[str] = []
    events: list[BaseEvent] = []
    for entity in entities:
        uid = entity.get("uid")
        if not uid:
            continue
        uid = str(uid)
        new_status = _status_of(entity.get("status"))
        prior_status = prior_status_by_uid.get(uid)
        if new_status == _COMPLETED and prior_status != _COMPLETED:
            event = _completion_event(entity_type, uid, entity)
            if event is not None:
                events.append(event)
        elif prior_status == _COMPLETED and new_status is not None and new_status != _COMPLETED:
            reopened.append(uid)

    return IngestStatusTransitions(tuple(reopened), tuple(events))


def _completion_event(
    entity_type: EntityType,
    uid: str,
    # boundary: see ``classify_ingest_status_transitions``.
    entity: dict[str, Any],
) -> BaseEvent | None:
    """Build the domain's completion event for one entity born or edited into ``completed``.

    Mirrors each domain's born-completed create-door publish
    (``*CoreService._publish_born_completed``) so the vault door and the create
    door announce a completion identically. ``occurred_at`` carries the entity's
    own completion stamp, which is what lets a historical vault line report the
    day it happened rather than the ingest moment. Returns ``None`` for the two
    stamping domains with no entity-completion event (Habit, Choice).
    """
    user_uid = UserUID(str(entity.get("user_uid") or ""))
    occurred_at = completion_moment(_stamp_of(entity_type, entity))

    if entity_type is EntityType.TASK:
        due_date = _as_date(entity.get("due_date"))
        actual_minutes = _as_int(entity.get("actual_minutes"))
        return TaskCompleted(
            task_uid=uid,
            user_uid=user_uid,
            completion_time_seconds=actual_minutes * 60 if actual_minutes is not None else None,
            # Measured against the completion moment, not today: a task
            # completed on time last March must not be announced overdue purely
            # because March has passed (the overdue branch APPENDS an insight).
            was_overdue=due_date < occurred_at.date() if due_date else False,
            is_repeat=False,
            occurred_at=occurred_at,
        )
    if entity_type is EntityType.GOAL:
        created_at = _as_datetime(entity.get("created_at"))
        return GoalAchieved(
            goal_uid=uid,
            user_uid=user_uid,
            # created_at → the completion moment, which is what the create door
            # measures too (there the two dates are the same moment). Measuring
            # to *now* instead would contradict this event's own occurred_at.
            # Floored at 0: a goal whose file authors no created_at is stamped
            # with the ingest moment, so a backdated achievement would otherwise
            # report a negative span — and the calibration handler reads a
            # negative ratio as "ahead of schedule". Zero is what the create door
            # reports for the same shape: no observed time in SKUEL.
            actual_duration_days=max((occurred_at - created_at).days, 0) if created_at else None,
            occurred_at=occurred_at,
        )
    if entity_type is EntityType.EVENT:
        return CalendarEventCompleted(
            event_uid=uid,
            user_uid=user_uid,
            completion_date=_as_date(entity.get("event_date")) or occurred_at.date(),
            # Honestly None on this door, as at the update chokepoint: the score
            # is owned by the progress / habit-completion services.
            quality_score=None,
            occurred_at=occurred_at,
        )
    return None


def _stamp_of(
    entity_type: EntityType,
    # boundary: see ``classify_ingest_status_transitions``.
    entity: dict[str, Any],
) -> date | datetime | None:
    """The domain's authored completion stamp, widened from whatever YAML produced.

    Task and Goal stamp a calendar date, the datetime domains a moment
    (``COMPLETION_FIELDS`` names the field), so the coercion follows the field
    rather than guessing from the value.
    """
    raw = entity.get(COMPLETION_FIELDS[entity_type])
    if entity_type in (EntityType.TASK, EntityType.GOAL):
        return _as_date(raw)
    return _as_datetime(raw)


def _status_of(value: Any) -> str | None:  # boundary: parsed YAML value
    """The canonical status string, or ``None`` when the entity declares none."""
    if isinstance(value, EntityStatus):
        return value.value
    if isinstance(value, str) and value:
        return value
    return None


def _as_date(value: Any) -> date | None:  # boundary: parsed YAML value
    """Read a date from YAML's ``date``/``datetime``/ISO-string forms; ``None`` otherwise."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _as_datetime(value: Any) -> datetime | None:  # boundary: parsed YAML value
    """Read a NAIVE datetime from YAML's ``datetime``/``date``/ISO-string forms.

    A bare date widens to midnight — the same widening ``completion_moment``
    applies, kept here so a ``created_at:`` authored as a plain day still yields
    a duration rather than nothing.

    An offset-bearing value is converted to UTC and stripped, because the
    values it has to meet are naive: ``BaseEvent.occurred_at`` is naive
    throughout, and so is everything ``completion_moment`` produces. The
    preparer canonicalizes ``created_at`` to a ``Z``-suffixed UTC string, so
    the mixed-awareness subtraction is not hypothetical — it is the ordinary
    case for an authored goal.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            widened = _as_date(value)
            if widened is None:
                return None
            parsed = datetime.combine(widened, datetime.min.time())
    else:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _as_int(value: Any) -> int | None:  # boundary: parsed YAML value
    """Read an int from YAML's numeric/string forms; ``None`` when it is neither."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None
