"""
Knowledge Credit Publisher — THE Activity → Knowledge Substance Chokepoint
==========================================================================

One function announces the knowledge an activity's write newly linked:
:func:`publish_knowledge_credit` turns ``(activity, the Kus its write CREATED a link
to)`` into its domain's substance event — single-item for one Ku, bulk for two or
more, never both (that would double-increment the counter). Every owner door that
links an activity to knowledge publishes through it: the create doors, the task edit,
the post-create link doors and the vault ingest of a file's ``connections``.

The caller hands in what its write created, never what a request asked for: a link
already there, an inferred link the owner's write promoted, and a refused or dangling
uid are not credited (Knowledge Substance Philosophy).

:data:`KNOWLEDGE_CREDIT_EDGES` names the edge each crediting activity type links
knowledge over. Three types credit at the link; the others do not:

- **Event** — its counter (``times_practiced_in_events``) credits a practice when the
  event is COMPLETED, for each Ku its ``APPLIES_KNOWLEDGE`` edges name
  (``PsPracticeService.handle_event_completed``). Crediting the link as well would
  count one event twice, and a scheduled event nobody attended as practice.
- **Goal, Principle** — no counter channel.
- **UserEntry** — its own two writers publish ``KnowledgeReflectedInEntry``.

See: /docs/architecture/knowledge_substance_philosophy.md
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from core.events import publish_event
from core.events.knowledge_substance_events import (
    KnowledgeAppliedInTask,
    KnowledgeBuiltIntoHabit,
    KnowledgeBulkAppliedInTask,
    KnowledgeBulkBuiltIntoHabit,
    KnowledgeBulkInformedChoice,
    KnowledgeInformedChoice,
)
from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from collections.abc import Sequence

    from core.models.type_hints import UserUID
    from core.ports.infrastructure_protocols import EventBusOperations

KNOWLEDGE_CREDIT_EDGES: Final[Mapping[EntityType, RelationshipName]] = {
    EntityType.TASK: RelationshipName.APPLIES_KNOWLEDGE,
    EntityType.HABIT: RelationshipName.REINFORCES_KNOWLEDGE,
    EntityType.CHOICE: RelationshipName.INFORMED_BY_KNOWLEDGE,
}


@dataclass(frozen=True, kw_only=True)
class KnowledgeCreditSource:
    """The activity whose new knowledge links are credited.

    ``priority`` rides on a task's event and ``frequency`` on a habit's; both are
    context for subscribers, which credit by ``knowledge_uid`` alone.
    """

    entity_type: EntityType
    uid: str
    user_uid: UserUID
    title: str | None = None
    priority: str | None = None
    frequency: str | None = None


async def publish_knowledge_credit(
    event_bus: EventBusOperations | None,
    source: KnowledgeCreditSource,
    knowledge_uids: Sequence[str],
    logger: Any = None,  # boundary: a stdlib or structlog logger, as publish_event takes
) -> None:
    """Announce ``knowledge_uids`` as newly linked to ``source``.

    A repeated uid is one credit: the subscriber increments once per uid it is handed.
    Nothing is published for no uids, nor for a type :data:`KNOWLEDGE_CREDIT_EDGES`
    does not name.
    """
    uids = tuple(dict.fromkeys(knowledge_uids))
    if not uids:
        return
    event: (
        KnowledgeAppliedInTask
        | KnowledgeBulkAppliedInTask
        | KnowledgeBuiltIntoHabit
        | KnowledgeBulkBuiltIntoHabit
        | KnowledgeInformedChoice
        | KnowledgeBulkInformedChoice
    )
    match source.entity_type:
        case EntityType.TASK if len(uids) == 1:
            event = KnowledgeAppliedInTask(
                knowledge_uid=uids[0],
                task_uid=source.uid,
                user_uid=source.user_uid,
                task_title=source.title,
                task_priority=source.priority,
            )
        case EntityType.TASK:
            event = KnowledgeBulkAppliedInTask(
                knowledge_uids=uids,
                task_uid=source.uid,
                user_uid=source.user_uid,
                task_title=source.title,
                task_priority=source.priority,
            )
        case EntityType.HABIT if len(uids) == 1:
            event = KnowledgeBuiltIntoHabit(
                knowledge_uid=uids[0],
                habit_uid=source.uid,
                user_uid=source.user_uid,
                habit_title=source.title,
                frequency=source.frequency,
            )
        case EntityType.HABIT:
            event = KnowledgeBulkBuiltIntoHabit(
                knowledge_uids=uids,
                habit_uid=source.uid,
                user_uid=source.user_uid,
                habit_title=source.title,
                frequency=source.frequency,
            )
        case EntityType.CHOICE if len(uids) == 1:
            event = KnowledgeInformedChoice(
                knowledge_uid=uids[0],
                choice_uid=source.uid,
                user_uid=source.user_uid,
                choice_title=source.title,
            )
        case EntityType.CHOICE:
            event = KnowledgeBulkInformedChoice(
                knowledge_uids=uids,
                choice_uid=source.uid,
                user_uid=source.user_uid,
                choice_title=source.title,
            )
        case _:
            return
    await publish_event(event_bus, event, logger)


__all__ = ["KNOWLEDGE_CREDIT_EDGES", "KnowledgeCreditSource", "publish_knowledge_credit"]
