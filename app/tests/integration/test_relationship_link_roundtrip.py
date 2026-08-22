"""Real-Neo4j guard tests for the UnifiedRelationshipService single-edge path.

`UnifiedRelationshipService.create_relationship` used to dispatch to a dynamically-named
`link_{domain}_to_{key}` *backend* method. Only two such methods ever existed
(`link_habit_to_knowledge`, `link_habit_to_principle`), so the call failed at runtime
("Backend method not found") for every other domain — including reachable routes
(`POST /goals/generate-tasks` → `link_task_to_knowledge`). The fix routes the single
method through the proven `backend.create_relationships_batch` path, keyed off the
registry spec.

Every facade `link_{domain}_to_{key}` method now passes its explicit registry method_key
straight to `create_relationship` (the candidate-list `link_to_*` wrappers were deleted):
the registry validates the key (fails closed on a typo) and orients direction. The static
half of that contract is guarded by tests/test_cross_domain_link_keys.py; these tests are
the dynamic half — they create the edge against a real Neo4j and read it back.

Mocked unit tests structurally cannot catch a wrong key (an `AsyncMock` resolves any
attribute and accepts any argument), which is why the `link_choice_to_habit` "habits"
typo survived undetected until the registry guard surfaced it.
"""

from datetime import date, timedelta

import pytest

from core.models.choice.choice import Choice
from core.models.curriculum import Curriculum
from core.models.enums import (
    Domain,
    EntityStatus,
    GoalTimeframe,
    GoalType,
    MeasurementType,
    Priority,
    RecurrencePattern,
    SELCategory,
)
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.entity_enums import EntityType
from core.models.enums.event_enums import AttendanceStatus
from core.models.enums.habit_enums import HabitCategory
from core.models.enums.principle_enums import PrincipleCategory
from core.models.event.event import Event
from core.models.event.event_request import AddAttendeeRequest, RemoveAttendeeRequest
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import HABITS_CONFIG
from core.models.task.task import Task
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService


@pytest.mark.asyncio
class TestRelationshipLinkRoundTrip:
    """End-to-end (real Neo4j) coverage for the single create_relationship path."""

    async def _make_ku(self, ku_backend, uid: str) -> None:
        ku = Curriculum(
            uid=uid, title=uid, domain=Domain.TECH, sel_category=SELCategory.SELF_AWARENESS
        )
        assert (await ku_backend.create(ku)).is_ok

    async def _make_task(self, services, uid: str) -> None:
        task = Task(
            uid=uid,
            title=uid,
            description="link round-trip fixture",
            user_uid="user_test",
            priority=Priority.MEDIUM,
            status=EntityStatus.DRAFT,
        )
        assert (await services.tasks.backend.create(task)).is_ok

    async def test_link_task_to_knowledge_creates_applies_knowledge_edge(
        self, services, ku_backend, clean_neo4j
    ):
        """The facade method that the /goals/generate-tasks route uses now writes a real edge.

        Pre-fix this dispatched to a non-existent `link_task_to_knowledge` backend method
        and failed at runtime.
        """
        await self._make_task(services, "task:link_ku_src")
        await self._make_ku(ku_backend, "ku:link_target")

        result = await services.tasks.link_task_to_knowledge("task:link_ku_src", "ku:link_target")
        assert result.is_ok, f"link_task_to_knowledge failed: {result}"

        edges = await services.tasks.backend.get_relationships(
            "task:link_ku_src", rel_type=RelationshipName.APPLIES_KNOWLEDGE, direction="outgoing"
        )
        assert edges.is_ok
        assert [r["type"] for r in edges.value] == ["APPLIES_KNOWLEDGE"]
        assert edges.value[0]["target_uid"] == "ku:link_target"

    async def test_create_relationship_single_persists_properties(
        self, services, ku_backend, clean_neo4j
    ):
        """The single create_relationship writes the registry-typed edge and persists properties."""
        await self._make_task(services, "task:link_props_src")
        await self._make_ku(ku_backend, "ku:link_props_target")

        result = await services.tasks.relationships.create_relationship(
            "knowledge",
            "task:link_props_src",
            "ku:link_props_target",
            properties={"confidence": 0.9},
        )
        assert result.is_ok
        assert result.value is True

        meta = await services.tasks.backend.get_relationship_metadata(
            from_uid="task:link_props_src",
            to_uid="ku:link_props_target",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
        )
        assert meta.is_ok
        assert meta.value is not None
        assert meta.value["confidence"] == 0.9

    async def test_habit_knowledge_link_still_reinforces_knowledge(
        self, habits_backend, ku_backend, clean_neo4j
    ):
        """No regression for the two cases that worked pre-fix via hand-written backend methods.

        The deleted `link_habit_to_knowledge` backend method created `REINFORCES_KNOWLEDGE`;
        the registry maps the habit `"knowledge"` key to the same edge type, so routing
        through the batch path is behaviour-preserving.
        """
        habit = Habit(
            uid="habit:link_ku_src",
            user_uid="user_test",
            entity_type=EntityType.HABIT,
            title="Habit",
            description="link round-trip fixture",
            habit_category=HabitCategory.LEARNING,
            status=EntityStatus.ACTIVE,
            recurrence_pattern=RecurrencePattern.DAILY,
        )
        assert (await habits_backend.create(habit)).is_ok
        await self._make_ku(ku_backend, "ku:habit_target")

        result = await UnifiedRelationshipService(
            backend=habits_backend, config=HABITS_CONFIG
        ).create_relationship("knowledge", "habit:link_ku_src", "ku:habit_target")
        assert result.is_ok
        assert result.value is True

        edges = await habits_backend.get_relationships(
            "habit:link_ku_src",
            rel_type=RelationshipName.REINFORCES_KNOWLEDGE,
            direction="outgoing",
        )
        assert edges.is_ok
        assert [r["type"] for r in edges.value] == ["REINFORCES_KNOWLEDGE"]
        assert edges.value[0]["target_uid"] == "ku:habit_target"

    async def test_incoming_spec_edge_is_oriented_related_to_owner(
        self, services, habits_backend, clean_neo4j
    ):
        """An incoming spec writes the edge related→owner, not owner→related.

        Goals ``supporting_habits`` is the registry-incoming ``SUPPORTS_GOAL``
        (``(Habit)-[:SUPPORTS_GOAL]->(Goal)``). Calling create_relationship with
        ``(goal, habit)`` must store ``habit→goal`` so the direction-aware reader sees
        it — writing ``goal→habit`` (the naive from→to) would be silently invisible.
        """
        today = date.today()
        goal = Goal(
            uid="goal:incoming_owner",
            user_uid="user_test",
            title="Goal",
            description="incoming-orientation fixture",
            goal_type=GoalType.LEARNING,
            domain=Domain.TECH,
            timeframe=GoalTimeframe.QUARTERLY,
            measurement_type=MeasurementType.PERCENTAGE,
            target_value=100.0,
            current_value=0.0,
            start_date=today,
            target_date=today + timedelta(days=90),
            status=EntityStatus.ACTIVE,
            priority=Priority.HIGH,
        )
        assert (await services.goals.backend.create(goal)).is_ok
        habit = Habit(
            uid="habit:incoming_related",
            user_uid="user_test",
            entity_type=EntityType.HABIT,
            title="Habit",
            description="incoming-orientation fixture",
            habit_category=HabitCategory.LEARNING,
            status=EntityStatus.ACTIVE,
            recurrence_pattern=RecurrencePattern.DAILY,
        )
        assert (await habits_backend.create(habit)).is_ok

        result = await services.goals.relationships.create_relationship(
            "supporting_habits", "goal:incoming_owner", "habit:incoming_related"
        )
        assert result.is_ok
        assert result.value is True

        # The goal has an INCOMING SUPPORTS_GOAL edge from the habit...
        incoming = await services.goals.backend.get_relationships(
            "goal:incoming_owner", rel_type=RelationshipName.SUPPORTS_GOAL, direction="incoming"
        )
        assert incoming.is_ok
        assert [r["type"] for r in incoming.value] == ["SUPPORTS_GOAL"]
        assert incoming.value[0]["target_uid"] == "habit:incoming_related"

        # ...and NOT a backwards outgoing edge from the goal.
        outgoing = await services.goals.backend.get_relationships(
            "goal:incoming_owner", rel_type=RelationshipName.SUPPORTS_GOAL, direction="outgoing"
        )
        assert outgoing.is_ok
        assert outgoing.value == []

        # Deletion must orient identically (owner/related order) — unlink actually removes it.
        deleted = await services.goals.relationships.delete_relationship(
            "supporting_habits", "goal:incoming_owner", "habit:incoming_related"
        )
        assert deleted.is_ok
        after = await services.goals.backend.get_relationships(
            "goal:incoming_owner", rel_type=RelationshipName.SUPPORTS_GOAL, direction="incoming"
        )
        assert after.is_ok
        assert after.value == []

    async def test_link_choice_to_habit_creates_impacts_habit_edge(
        self, services, habits_backend, clean_neo4j
    ):
        """link_choice_to_habit writes a real IMPACTS_HABIT edge with its property.

        Pre-fix this facade passed the key ``"habits"``, which is not a method_key in
        CHOICES_CONFIG (the Choice→Habit edge is ``impacted_habits``/IMPACTS_HABIT), so
        create_relationship failed config validation and the link was silently dropped.
        A mocked unit test passed regardless because the AsyncMock accepted ``"habits"``.
        """
        choice = Choice(
            uid="choice:link_habit_src",
            title="Choice",
            description="choice→habit link round-trip fixture",
            user_uid="user_test",
            choice_type=ChoiceType.MULTIPLE,
            status=EntityStatus.DRAFT,
            priority=Priority.MEDIUM,
            domain=Domain.TECH,
        )
        assert (await services.choices.backend.create(choice)).is_ok
        habit = Habit(
            uid="habit:link_choice_target",
            user_uid="user_test",
            entity_type=EntityType.HABIT,
            title="Habit",
            description="choice→habit link round-trip fixture",
            habit_category=HabitCategory.LEARNING,
            status=EntityStatus.ACTIVE,
            recurrence_pattern=RecurrencePattern.DAILY,
        )
        assert (await habits_backend.create(habit)).is_ok

        result = await services.choices.link_choice_to_habit(
            "choice:link_habit_src", "habit:link_choice_target", reinforcement_strength=0.7
        )
        assert result.is_ok, f"link_choice_to_habit failed: {result}"

        edges = await services.choices.backend.get_relationships(
            "choice:link_habit_src",
            rel_type=RelationshipName.IMPACTS_HABIT,
            direction="outgoing",
        )
        assert edges.is_ok
        assert [r["type"] for r in edges.value] == ["IMPACTS_HABIT"]
        assert edges.value[0]["target_uid"] == "habit:link_choice_target"

    async def _read_attends_edge(self, neo4j_driver, user_uid: str, event_uid: str):
        """Raw read of the (User)-[:ATTENDS]->(Event) edge props (None when absent)."""
        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (u:User {uid: $user_uid})-[r:ATTENDS]->(e:Entity {uid: $event_uid}) "
                "RETURN properties(r) AS props",
                user_uid=user_uid,
                event_uid=event_uid,
            )
            record = await result.single()
            return dict(record["props"]) if record else None

    async def test_attends_round_trip_consent_state_machine(
        self, services, neo4j_driver, clean_neo4j
    ):
        """The ADR-086 attendance triple: ATTENDS edge shape + consent semantics.

        (Retargeted from the former HAS_EVENT participation triple — the paper
        ownership channel deleted by the ownership-bundle arc.) Covers: organizer
        invite writes `invited` with the ACTOR as added_by; a stranger is refused;
        the organizer cannot revoke an accepted attendance; the target may always
        remove their own.
        """
        event = Event(
            uid="event:attendee_rt",
            user_uid="user_test",
            title="Event",
            description="attendee round-trip fixture",
            event_date=date.today(),
            event_type="work",
            status=EntityStatus.SCHEDULED,
            priority=Priority.MEDIUM,
        )
        assert (await services.events.backend.create(event)).is_ok

        # Organizer (event owner) invites the target → status "invited", actor stamped.
        added = await services.events.add_attendee(
            AddAttendeeRequest(
                event_uid="event:attendee_rt",
                user_uid="user_test_456",
                send_notification=False,
            ),
            actor_uid="user_test",
        )
        assert added.is_ok, f"add_attendee failed: {added}"

        props = await self._read_attends_edge(neo4j_driver, "user_test_456", "event:attendee_rt")
        assert props is not None, "organizer invite must write an ATTENDS edge"
        assert props["status"] == AttendanceStatus.INVITED.value
        assert props["added_by"] == "user_test"  # the ACTOR, not the target
        assert props["role"] == "attendee"
        assert props["joined_at"] is not None

        attendees = await services.events.get_event_attendees("event:attendee_rt")
        assert attendees.is_ok, f"get_event_attendees failed: {attendees}"
        assert "user_test_456" in attendees.value

        # A stranger (neither owner nor target) is refused.
        stranger_add = await services.events.add_attendee(
            AddAttendeeRequest(
                event_uid="event:attendee_rt",
                user_uid="user_test_456",
                send_notification=False,
            ),
            actor_uid="user_test_123",
        )
        assert stranger_add.is_error, "a non-owner, non-target actor must be refused"

        # Target self-adds → accepts their own pending invite (only the target transitions).
        accepted = await services.events.add_attendee(
            AddAttendeeRequest(
                event_uid="event:attendee_rt",
                user_uid="user_test_456",
                send_notification=False,
            ),
            actor_uid="user_test_456",
        )
        assert accepted.is_ok, f"self-add (accept) failed: {accepted}"
        props = await self._read_attends_edge(neo4j_driver, "user_test_456", "event:attendee_rt")
        assert props is not None
        assert props["status"] == AttendanceStatus.ACCEPTED.value
        assert props["added_by"] == "user_test"  # ON CREATE only — never rewritten

        # Organizer may NOT revoke an accepted attendance (only a pending invite).
        organizer_remove = await services.events.remove_attendee(
            RemoveAttendeeRequest(
                event_uid="event:attendee_rt",
                user_uid="user_test_456",
                send_notification=False,
            ),
            actor_uid="user_test",
        )
        assert organizer_remove.is_ok
        assert organizer_remove.value is False, "accepted attendance is the attendee's to keep"
        still = await services.events.get_event_attendees("event:attendee_rt")
        assert still.is_ok and "user_test_456" in still.value

        # The target may always remove their own attendance.
        removed = await services.events.remove_attendee(
            RemoveAttendeeRequest(
                event_uid="event:attendee_rt",
                user_uid="user_test_456",
                send_notification=False,
            ),
            actor_uid="user_test_456",
        )
        assert removed.is_ok
        assert removed.value is True
        after = await services.events.get_event_attendees("event:attendee_rt")
        assert after.is_ok
        assert "user_test_456" not in after.value

    async def test_principle_alignment_keys_resolve_and_read_back(
        self, services, habits_backend, clean_neo4j
    ):
        """The dual-track alignment read keys resolve and return data on a real Neo4j.

        `_calculate_system_alignment_for_dual_track` reads goals via `"guided_goals"`
        (GUIDES_GOAL) and habits via `"inspired_habits"` (INSPIRES_HABIT) through the
        2-arg service `get_related_uids(method_key, uid)`. Pre-fix it called the 3-arg
        *backend* signature (`get_related_uids(uid, REL, "incoming")` → TypeError, swallowed
        by the dual-track try/except) and used the phantom key `"habits"` — so system
        alignment silently scored nothing. These are the exact calls the fixed method makes.
        """
        principle = Principle(
            uid="principle:align_rt",
            user_uid="user_test",
            title="Principle",
            statement="alignment round-trip fixture",
            description="alignment round-trip fixture",
            principle_category=PrincipleCategory.INTELLECTUAL,
        )
        assert (await services.principles.backend.create(principle)).is_ok

        today = date.today()
        goal = Goal(
            uid="goal:align_rt",
            user_uid="user_test",
            title="Goal",
            description="alignment round-trip fixture",
            goal_type=GoalType.LEARNING,
            domain=Domain.TECH,
            timeframe=GoalTimeframe.QUARTERLY,
            measurement_type=MeasurementType.PERCENTAGE,
            target_value=100.0,
            current_value=0.0,
            start_date=today,
            target_date=today + timedelta(days=90),
            status=EntityStatus.ACTIVE,
            priority=Priority.HIGH,
        )
        assert (await services.goals.backend.create(goal)).is_ok
        habit = Habit(
            uid="habit:align_rt",
            user_uid="user_test",
            entity_type=EntityType.HABIT,
            title="Habit",
            description="alignment round-trip fixture",
            habit_category=HabitCategory.LEARNING,
            status=EntityStatus.ACTIVE,
            recurrence_pattern=RecurrencePattern.DAILY,
        )
        assert (await habits_backend.create(habit)).is_ok

        rels = services.principles.relationships
        assert (
            await rels.create_relationship("guided_goals", "principle:align_rt", "goal:align_rt")
        ).is_ok
        assert (
            await rels.create_relationship(
                "inspired_habits", "principle:align_rt", "habit:align_rt"
            )
        ).is_ok

        # The exact 2-arg service reads the fixed method performs:
        goals_read = await rels.get_related_uids("guided_goals", "principle:align_rt")
        assert goals_read.is_ok, f"guided_goals read failed: {goals_read}"
        assert goals_read.value == ["goal:align_rt"]

        habits_read = await rels.get_related_uids("inspired_habits", "principle:align_rt")
        assert habits_read.is_ok, f"inspired_habits read failed: {habits_read}"
        assert habits_read.value == ["habit:align_rt"]
