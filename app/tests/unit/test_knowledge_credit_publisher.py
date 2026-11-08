"""``publish_knowledge_credit`` — one event per credit, of the activity's own channel.

- One Ku is the single-item event; two or more are one bulk event, in the order
  given, each uid once. Never both: the subscriber increments once per uid handed.
- A task, a habit and a choice each publish their own channel's event; the table of
  crediting types is exactly those three.
- An event, a goal and a principle publish nothing; nor does an empty list.
"""

from __future__ import annotations

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from core.events.knowledge_credit_publisher import (
    KNOWLEDGE_CREDIT_EDGES,
    KnowledgeCreditSource,
    publish_knowledge_credit,
)
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
from core.models.type_hints import UserUID

OWNER = UserUID("user_c4ed170000000000")


def _source(entity_type: EntityType) -> KnowledgeCreditSource:
    return KnowledgeCreditSource(
        entity_type=entity_type,
        uid=f"{entity_type.value}_c4ed170000000000",
        user_uid=OWNER,
        title="Water the plants",
        priority="high",
        frequency="daily",
    )


async def _published(entity_type: EntityType, knowledge_uids: list[str]) -> list[object]:
    bus = InMemoryEventBus(capture_history=True)
    await publish_knowledge_credit(bus, _source(entity_type), knowledge_uids)
    return bus.get_event_history()


def test_the_crediting_types_are_task_habit_and_choice() -> None:
    assert dict(KNOWLEDGE_CREDIT_EDGES) == {
        EntityType.TASK: RelationshipName.APPLIES_KNOWLEDGE,
        EntityType.HABIT: RelationshipName.REINFORCES_KNOWLEDGE,
        EntityType.CHOICE: RelationshipName.INFORMED_BY_KNOWLEDGE,
    }


async def test_one_ku_is_the_single_event_of_each_channel() -> None:
    task = _source(EntityType.TASK)
    habit = _source(EntityType.HABIT)
    choice = _source(EntityType.CHOICE)

    [applied] = await _published(EntityType.TASK, ["ku.care.water"])
    [built] = await _published(EntityType.HABIT, ["ku.care.water"])
    [informed] = await _published(EntityType.CHOICE, ["ku.care.water"])

    assert isinstance(applied, KnowledgeAppliedInTask)
    assert (applied.knowledge_uid, applied.task_uid, applied.task_priority) == (
        "ku.care.water",
        task.uid,
        "high",
    )
    assert isinstance(built, KnowledgeBuiltIntoHabit)
    assert (built.knowledge_uid, built.habit_uid, built.frequency) == (
        "ku.care.water",
        habit.uid,
        "daily",
    )
    assert isinstance(informed, KnowledgeInformedChoice)
    assert (informed.knowledge_uid, informed.choice_uid) == ("ku.care.water", choice.uid)


async def test_two_kus_are_one_bulk_event_each_uid_once_in_order() -> None:
    uids = ["ku.care.water", "ku.care.light", "ku.care.water"]

    [applied] = await _published(EntityType.TASK, uids)
    [built] = await _published(EntityType.HABIT, uids)
    [informed] = await _published(EntityType.CHOICE, uids)

    assert isinstance(applied, KnowledgeBulkAppliedInTask)
    assert isinstance(built, KnowledgeBulkBuiltIntoHabit)
    assert isinstance(informed, KnowledgeBulkInformedChoice)
    for event in (applied, built, informed):
        assert event.knowledge_uids == ("ku.care.water", "ku.care.light")
        assert event.user_uid == OWNER


async def test_a_repeated_single_ku_is_the_single_event() -> None:
    [applied] = await _published(EntityType.TASK, ["ku.care.water", "ku.care.water"])

    assert isinstance(applied, KnowledgeAppliedInTask)


@pytest.mark.parametrize("entity_type", [EntityType.EVENT, EntityType.GOAL, EntityType.PRINCIPLE])
async def test_a_type_with_no_credit_at_the_link_publishes_nothing(
    entity_type: EntityType,
) -> None:
    assert await _published(entity_type, ["ku.care.water"]) == []


async def test_no_kus_publish_nothing() -> None:
    assert await _published(EntityType.TASK, []) == []
