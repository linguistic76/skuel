"""Real-Neo4j round-trip for the edges Goal and Habit creation now writes.

Sibling of ``test_choice_knowledge_edge_roundtrip.py``. The unit suite
(``tests/unit/test_goal_habit_create_edges.py``) stubs the backend, so it proves
the service ASKS for the right edges with the right properties. It cannot prove
the edge is real, correctly oriented, or visible to the readers that were empty
— and "the writer is wired" was never the interesting half of this bug.

What was broken
---------------
Goals  ``parent_goal_uid`` set the ``Goal.fulfills_goal_uid`` node property and
       nothing else. Every hierarchy reader traverses the EDGE instead, so
       ``get_subgoals`` (``GET /api/goals/children``) returned nothing for a goal
       the create form had just given a parent. The reader is exercised here
       directly, not simulated with a hand-written MATCH.

Habits The four link lists (knowledge / principles / goals / prerequisite habits)
       were dropped entirely. All four name relationships HABITS_CONFIG declares
       and live code reads.

Direction matters and is asserted: all four Habit specs are declared ``outgoing``
from the habit, and the goal hierarchy is ``(parent)-[:HAS_SUBGOAL]->(child)``
with the inverse ``SUBGOAL_OF`` written alongside. An edge written backwards
persists perfectly and reads back empty — which is the failure mode a
direction-blind assertion would miss.
"""

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.backends.activity_backends import GoalsBackend, HabitsBackend
from core.models.enums import Domain, MeasurementType, Priority, RecurrencePattern
from core.models.enums.neo_labels import NeoLabel
from core.models.goal.goal import Goal
from core.models.goal.goal_request import GoalCreateRequest
from core.models.habit.habit import Habit
from core.models.habit.habit_request import HabitCreateRequest
from core.models.relationship_names import RelationshipName
from core.services.goals.goals_core_service import GoalsCoreService
from core.services.habits.habits_core_service import HabitsCoreService


@pytest_asyncio.fixture
async def event_bus():
    return InMemoryEventBus(capture_history=True)


@pytest_asyncio.fixture
async def goals_service(neo4j_driver, clean_neo4j, event_bus):
    # Multi-label (:Goal:Entity) to match production — the relationship registry keys
    # its edge validation off the domain label.
    backend = GoalsBackend(neo4j_driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY)
    return GoalsCoreService(backend=backend, event_bus=event_bus)


@pytest_asyncio.fixture
async def habits_service(neo4j_driver, clean_neo4j, event_bus):
    backend = HabitsBackend(neo4j_driver, NeoLabel.HABIT, Habit, base_label=NeoLabel.ENTITY)
    return HabitsCoreService(backend=backend, event_bus=event_bus)


@pytest_asyncio.fixture
async def test_user_uid(neo4j_driver, clean_neo4j):
    uid = "user_test_create_edges"
    async with neo4j_driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()", uid=uid
        )
    return uid


def goal_request(**overrides):
    defaults = {
        "title": "Parent goal",
        "description": "Umbrella goal for the quarter",
        "domain": Domain.TECH,
        "priority": Priority.HIGH,
        "measurement_type": MeasurementType.NUMERIC,
        "target_value": 100.0,
    }
    defaults.update(overrides)
    return GoalCreateRequest(**defaults)


async def _create_node(neo4j_driver, uid: str, labels: str, entity_type: str, title: str) -> None:
    """Persist a minimal target node so the batch's registry validation passes."""
    async with neo4j_driver.session() as session:
        await session.run(
            f"MERGE (n:{labels} {{uid: $uid}}) "
            "ON CREATE SET n.entity_type = $entity_type, n.title = $title",
            uid=uid,
            entity_type=entity_type,
            title=title,
        )


@pytest.mark.asyncio
class TestGoalHierarchyEdgeRoundTrip:
    """The HAS_SUBGOAL edge must be real and visible to the hierarchy readers."""

    async def test_subgoal_is_visible_to_the_children_reader(
        self, goals_service, test_user_uid
    ) -> None:
        """``get_subgoals`` — what ``GET /api/goals/children`` calls — must find it.

        This is the assertion the whole change exists for: before it, the property
        was set and this read returned an empty list.
        """
        parent = await goals_service.create_goal(goal_request(), test_user_uid)
        assert parent.is_ok, f"parent create failed: {parent.error}"

        child = await goals_service.create_goal(
            goal_request(title="Subgoal", parent_goal_uid=parent.value.uid), test_user_uid
        )
        assert child.is_ok, f"subgoal create failed: {child.error}"

        children = await goals_service.get_subentities(parent.value.uid)
        assert children.is_ok, f"get_subgoals failed: {children.error}"
        assert [g.uid for g in children.value] == [child.value.uid], (
            "the parent's children read is empty — the subgoal reached the graph as a "
            "node property with no HAS_SUBGOAL edge behind it"
        )

    async def test_parent_reader_resolves_the_other_way(self, goals_service, test_user_uid) -> None:
        """``get_parent_goal`` traverses the INVERSE edge, written in the same MERGE.

        Asserting only the forward direction would pass against a create that wrote
        HAS_SUBGOAL and skipped SUBGOAL_OF, leaving ``/api/goals/parent`` broken.
        """
        parent = await goals_service.create_goal(goal_request(), test_user_uid)
        child = await goals_service.create_goal(
            goal_request(title="Subgoal", parent_goal_uid=parent.value.uid), test_user_uid
        )

        found = await goals_service.get_parent_entity(child.value.uid)
        assert found.is_ok, f"get_parent_goal failed: {found.error}"
        assert found.value is not None, "the subgoal has no parent via SUBGOAL_OF"
        assert found.value.uid == parent.value.uid

    async def test_progress_weight_persists_on_the_edge(
        self, goals_service, neo4j_driver, test_user_uid
    ) -> None:
        """``progress_weight`` is an EDGE property — it must be readable off the edge.

        Read with an explicit MATCH because no goal reader consumes it yet (Tasks'
        ``calculate_parent_progress`` is the only weighted-progress query today).
        That is exactly why it needs pinning: nothing else would notice it vanishing.
        """
        parent = await goals_service.create_goal(goal_request(), test_user_uid)
        child = await goals_service.create_goal(
            goal_request(
                title="Quarter-weight subgoal",
                parent_goal_uid=parent.value.uid,
                progress_weight=0.25,
            ),
            test_user_uid,
        )
        assert child.is_ok, f"subgoal create failed: {child.error}"

        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (p {uid: $parent})-[r:HAS_SUBGOAL]->(c {uid: $child}) "
                "RETURN r.progress_weight AS weight",
                parent=parent.value.uid,
                child=child.value.uid,
            )
            row = await result.single()

        assert row is not None, "no HAS_SUBGOAL edge between the two goals"
        assert row["weight"] == 0.25

    async def test_parentless_goal_gets_no_hierarchy_edge(
        self, goals_service, neo4j_driver, test_user_uid
    ) -> None:
        """Positive control against a create that links unconditionally."""
        goal = await goals_service.create_goal(goal_request(title="Standalone"), test_user_uid)
        assert goal.is_ok, f"create failed: {goal.error}"

        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (g {uid: $uid})-[r:HAS_SUBGOAL|SUBGOAL_OF]-() RETURN count(r) AS n",
                uid=goal.value.uid,
            )
            row = await result.single()

        assert row["n"] == 0, "a goal with no parent still acquired a hierarchy edge"


@pytest.mark.asyncio
class TestHabitLinkEdgeRoundTrip:
    """The four link lists must persist as real, correctly-oriented edges."""

    async def test_all_four_link_lists_round_trip(
        self, habits_service, neo4j_driver, test_user_uid
    ) -> None:
        """RED before the fix: every one of these lists was silently discarded."""
        await _create_node(neo4j_driver, "ku_habit_link_abc", "Entity:Ku", "ku", "Deep Work")
        await _create_node(
            neo4j_driver, "principle_habit_link_abc", "Entity:Principle", "principle", "Focus"
        )
        await _create_node(neo4j_driver, "goal_habit_link_abc", "Entity:Goal", "goal", "Ship it")
        await _create_node(neo4j_driver, "habit_prereq_abc", "Entity:Habit", "habit", "Wake at six")

        result = await habits_service.create_habit(
            HabitCreateRequest(
                title="Morning deep work",
                description="Ninety minutes before email",
                recurrence_pattern=RecurrencePattern.DAILY,
                target_days_per_week=7,
                linked_knowledge_uids=["ku_habit_link_abc"],
                linked_principle_uids=["principle_habit_link_abc"],
                linked_goal_uids=["goal_habit_link_abc"],
                prerequisite_habit_uids=["habit_prereq_abc"],
            ),
            test_user_uid,
        )
        assert result.is_ok, f"create_habit failed: {result.error}"
        habit = result.value

        for relationship, target in (
            (RelationshipName.REINFORCES_KNOWLEDGE, "ku_habit_link_abc"),
            (RelationshipName.EMBODIES_PRINCIPLE, "principle_habit_link_abc"),
            (RelationshipName.SUPPORTS_GOAL, "goal_habit_link_abc"),
            (RelationshipName.REQUIRES_PREREQUISITE_HABIT, "habit_prereq_abc"),
        ):
            # direction="outgoing" is the assertion, not a filter: every one of the
            # four specs is declared outgoing from the habit, so an edge written
            # backwards would persist and read back empty here.
            edges = await habits_service.backend.get_relationships(
                habit.uid, rel_type=relationship, direction="outgoing"
            )
            assert edges.is_ok, f"{relationship.value} read failed: {edges.error}"
            assert [r["target_uid"] for r in edges.value] == [target], (
                f"{relationship.value} did not round-trip to {target}: {edges.value}"
            )

    async def test_supports_goal_carries_the_essentiality_tier(
        self, habits_service, neo4j_driver, test_user_uid
    ) -> None:
        """GOAPS resolves the habit tiers by filtering SUPPORTS_GOAL on this property.

        An unstamped edge is not merely untidy — it disappears from every filtered
        tier read. Pinned against the value ``link_goal_to_habit`` writes by default.
        """
        await _create_node(neo4j_driver, "goal_essentiality_abc", "Entity:Goal", "goal", "Ship")

        result = await habits_service.create_habit(
            HabitCreateRequest(
                title="Weekly review",
                recurrence_pattern=RecurrencePattern.WEEKLY,
                target_days_per_week=1,
                linked_goal_uids=["goal_essentiality_abc"],
            ),
            test_user_uid,
        )
        assert result.is_ok, f"create_habit failed: {result.error}"

        async with neo4j_driver.session() as session:
            row = await (
                await session.run(
                    "MATCH (h {uid: $habit})-[r:SUPPORTS_GOAL]->(g {uid: $goal}) "
                    "RETURN r.essentiality AS essentiality, r.weight AS weight",
                    habit=result.value.uid,
                    goal="goal_essentiality_abc",
                )
            ).single()

        assert row is not None, "no SUPPORTS_GOAL edge was written"
        assert row["essentiality"] == "supporting"
        assert row["weight"] == 1.0

    async def test_linkless_habit_creates_no_edges(
        self, habits_service, neo4j_driver, test_user_uid
    ) -> None:
        """Positive control: the batch is skipped, and nothing else sneaks an edge in."""
        result = await habits_service.create_habit(
            HabitCreateRequest(
                title="Stretch",
                recurrence_pattern=RecurrencePattern.DAILY,
                target_days_per_week=7,
            ),
            test_user_uid,
        )
        assert result.is_ok, f"create_habit failed: {result.error}"

        async with neo4j_driver.session() as session:
            row = await (
                await session.run(
                    "MATCH (h {uid: $uid})-[r:REINFORCES_KNOWLEDGE|EMBODIES_PRINCIPLE"
                    "|SUPPORTS_GOAL|REQUIRES_PREREQUISITE_HABIT]->() RETURN count(r) AS n",
                    uid=result.value.uid,
                )
            ).single()

        assert row["n"] == 0, "a habit with no link lists still acquired link edges"
