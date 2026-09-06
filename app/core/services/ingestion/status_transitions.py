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
     /docs/roadmap/done/vault-task-door-no-events.md
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import Any

from core.events import BaseEvent, CalendarEventCompleted, GoalAchieved, TaskCompleted
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.type_hints import UserUID
from core.services.completion_stamp import COMPLETION_FIELDS, completion_moment

__all__ = [
    "EVENT_SOURCE_FIELDS",
    "IngestStatusTransitions",
    "build_completion_events",
    "classify_ingest_status_transitions",
]

_COMPLETED = EntityStatus.COMPLETED.value


@dataclass(frozen=True)
class IngestStatusTransitions:
    """What one persisted batch's status changes oblige the door to do.

    ``reopened_uids`` are the entities whose completion stamp must be removed;
    ``completed_uids`` are the ones that transitioned INTO completed and owe a
    domain event. Both are empty for a batch that changed no entity's completion
    state — the ordinary case, and the one a ``--force`` re-ingest must produce.

    The events are built separately (:func:`build_completion_events`) because
    they describe the entity as PERSISTED, which needs a read the classification
    itself cannot do.
    """

    reopened_uids: tuple[str, ...] = ()
    completed_uids: tuple[str, ...] = ()


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
            them — ``status`` is the NEW status, and its ABSENCE as a key is
            distinct from its presence holding ``None`` (see the loop).
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
    completed: list[str] = []
    for entity in entities:
        uid = entity.get("uid")
        if not uid:
            continue
        uid = str(uid)
        # Presence, not truthiness: the upsert's ``SET n += props`` writes
        # whatever key the file declares, and a null value REMOVES the stored
        # property. So an absent ``status:`` key leaves the stored status alone
        # (no transition either way), while a present-but-empty one
        # (``status:`` / ``status: none``, both of which the ingest validator
        # deliberately admits as absence) deletes it — leaving an entity that is
        # definitively no longer completed. Only the second is a reopen. This is
        # where the ingest door's reading legitimately differs from
        # ``is_reopen_transition``: there a null status means "not changing the
        # status", here it means "erase it".
        declares_status = "status" in entity
        new_status = _status_of(entity.get("status"))
        prior_status = prior_status_by_uid.get(uid)
        if new_status == _COMPLETED and prior_status != _COMPLETED:
            completed.append(uid)
        elif prior_status == _COMPLETED and declares_status and new_status != _COMPLETED:
            reopened.append(uid)

    return IngestStatusTransitions(tuple(reopened), tuple(completed))


#: The node properties each domain's completion event reads, beyond the status
#: itself. Published so the caller can fetch exactly these back from the graph:
#: an event describes the entity as PERSISTED, and the file payload is only the
#: half the file happens to declare (``SET n += props`` keeps every property the
#: frontmatter omits, so a file that changes nothing but ``status`` still leaves
#: a due date and an elapsed duration standing on the node).
EVENT_SOURCE_FIELDS: Mapping[EntityType, tuple[str, ...]] = MappingProxyType(
    {
        EntityType.TASK: ("user_uid", "completion_date", "due_date", "actual_minutes"),
        EntityType.GOAL: ("user_uid", "achieved_date", "created_at"),
        EntityType.EVENT: ("user_uid", "completed_at", "event_date"),
    }
)


def build_completion_events(
    entity_type: EntityType,
    completed_uids: tuple[str, ...],
    # boundary: node properties read back from Neo4j — heterogeneous per domain
    # (dates, ints, strings), narrowed by the coercions below.
    persisted_by_uid: Mapping[str, Mapping[str, Any]],
) -> tuple[BaseEvent, ...]:
    """Build the completion events a classified batch owes, from PERSISTED state.

    ``persisted_by_uid`` holds the properties named by :data:`EVENT_SOURCE_FIELDS`
    read back AFTER the upsert, which is the only honest source: the upsert merges
    (``SET n += props``), so the file payload is a subset of what the node ends up
    holding and an event built from it would report a task as neither overdue nor
    timed while the persisted task carries both.

    Mirrors each domain's born-completed create-door publish
    (``*CoreService._publish_born_completed``) so the vault door and the create
    door announce a completion identically. Habit and Choice yield nothing: their
    events (``HabitCompleted`` — a daily occurrence, ``ChoiceMade`` — the decide
    moment) describe different moments than the entity retiring.

    A uid with no persisted row is skipped rather than guessed at: it means the
    node vanished between the write and this read, and an event about an entity
    that is gone has nobody to serve.
    """
    if entity_type not in EVENT_SOURCE_FIELDS:
        return ()
    events: list[BaseEvent] = []
    for uid in completed_uids:
        persisted = persisted_by_uid.get(uid)
        if persisted is None:
            continue
        event = _completion_event(entity_type, uid, persisted)
        if event is not None:
            events.append(event)
    return tuple(events)


def _completion_event(
    entity_type: EntityType,
    uid: str,
    # boundary: node properties read back from Neo4j (see ``build_completion_events``).
    entity: Mapping[str, Any],
) -> BaseEvent | None:
    """Build one domain completion event from the entity's persisted properties.

    ``occurred_at`` carries the entity's own completion stamp, which is what lets
    a historical vault line report the day it happened rather than the ingest
    moment. Returns ``None`` for the two stamping domains with no
    entity-completion event (Habit, Choice).
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
    # boundary: node properties read back from Neo4j (see ``build_completion_events``).
    entity: Mapping[str, Any],
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


def _to_native(value: Any) -> Any:  # boundary: a Neo4j property value
    """Unwrap a ``neo4j.time`` temporal into its Python equivalent; pass anything else through.

    The driver hands back ``neo4j.time.Date``/``DateTime`` rather than ``date``/
    ``datetime``, and neither is an instance of the stdlib type, so every
    coercion below would fall through to ``None`` without this.
    """
    if getattr(type(value), "__module__", "") == "neo4j.time":
        to_native = getattr(value, "to_native", None)
        if to_native is not None:
            return to_native()
    return value


def _as_date(value: Any) -> date | None:  # boundary: a Neo4j property value
    """Read a date from ``date``/``datetime``/neo4j-temporal/ISO-string forms."""
    value = _to_native(value)
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


def _as_datetime(value: Any) -> datetime | None:  # boundary: a Neo4j property value
    """Read a NAIVE datetime from ``datetime``/``date``/neo4j-temporal/ISO-string forms.

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
    value = _to_native(value)
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


def _as_int(value: Any) -> int | None:  # boundary: a Neo4j property value
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
