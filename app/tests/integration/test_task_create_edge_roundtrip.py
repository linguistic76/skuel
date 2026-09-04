"""Real-Neo4j round-trip for the edges Task creation now writes.

Sibling of ``test_goal_habit_create_edge_roundtrip.py`` (#965). The unit suite
(``tests/unit/test_task_create_edges.py``) stubs the backend, so it proves the service
ASKS for the right edges with the right properties. It cannot prove the edge is real,
correctly oriented, or visible to the readers that were empty — and "the writer is wired"
was never the interesting half of this bug.

What was broken (measured 2026-08-05, both doors)
--------------------------------------------------
``parent_uid``  The generated CRUD route set it on the ``Task``, the mapper dropped it
                (it is in RELATIONSHIP_SKIP_FIELDS), and nothing on that path wrote the
                edge — only ``create_task`` called ``create_subtask_relationship``. So a
                subtask created through ``POST /api/tasks/create`` had no parent in the
                property AND no parent in the graph. ``get_subtasks`` is exercised here
                directly, not simulated with a hand-written MATCH.

``reinforces_habit_uid``
                The exact inverse: the converter set it, the mapper did NOT skip it, so it
                persisted as a node PROPERTY that no reader consults — while no
                REINFORCES_HABIT edge was written.

Both fields ride on the ``Task``, so both doors can write them; the edge write therefore
lives on the shared ``create`` primitive. That is what these tests exercise through the
ROUTE door, which is where both defects were.

Direction matters and is asserted. The hierarchy is ``(parent)-[:HAS_SUBTASK]->(child)``
with the inverse ``SUBTASK_OF`` written alongside, and REINFORCES_HABIT is declared
outgoing from the task. An edge written backwards persists perfectly and reads back
empty — the failure mode a direction-blind assertion would miss.

Ownership is asserted here rather than only in the unit suite because the rule is about
DATA the stub cannot model. Every endpoint is request input: ``create_hierarchy_relationship``
matches on UID and label with no owner filter, so a cross-user parent must be refused. The
counterpart control matters just as much — a Ku carries no owner at all and MUST stay
linkable, so "owned by nobody" has to mean allowed, not refused.
"""

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.backends.activity_backends import TasksBackend
from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.enums import EntityStatus, Priority
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.task.task_request import TaskCreateRequest
from core.services.conversion_service import ConversionServiceV2
from core.services.cross_domain import CrossDomainQueryService
from core.services.tasks.tasks_core_service import TasksCoreService

OTHER_USER = "user_test_task_edges_victim"


@pytest_asyncio.fixture
async def event_bus():
    return InMemoryEventBus(capture_history=True)


@pytest_asyncio.fixture
async def tasks_service(neo4j_driver, clean_neo4j, event_bus):
    # Multi-label (:Task:Entity) to match production — the relationship registry keys its
    # edge validation off the domain label.
    backend = TasksBackend(neo4j_driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)
    return TasksCoreService(backend=backend, event_bus=event_bus)


@pytest_asyncio.fixture
async def test_user_uid(neo4j_driver, clean_neo4j):
    uid = "user_test_task_create_edges"
    async with neo4j_driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()", uid=uid
        )
    return uid


def task_request(**overrides):
    defaults = {
        "title": "Parent task",
        "description": "Umbrella task for the migration",
        "priority": Priority.HIGH,
    }
    defaults.update(overrides)
    return TaskCreateRequest(**defaults)


async def _create_node(neo4j_driver, uid, labels, entity_type, title, user_uid=None):
    """Persist a minimal target node so the batch's registry validation passes.

    ``user_uid=None`` leaves the node UNOWNED, which is how shared content (a Ku) looks
    to the admission guard — the control that keeps knowledge links working.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            f"MERGE (n:{labels} {{uid: $uid}}) "
            "ON CREATE SET n.entity_type = $entity_type, n.title = $title, "
            "n.user_uid = $user_uid",
            uid=uid,
            entity_type=entity_type,
            title=title,
            user_uid=user_uid,
        )


async def _route_create(service, request, uid, user_uid):
    """DOOR A — build the entity exactly as ``CRUDRouteFactory`` does, then ``create``.

    Both defects lived on this door, so every headline assertion goes through it rather
    than through ``create_task``.
    """
    entity = ConversionServiceV2.task_create_to_pure(request, uid, user_uid=user_uid)
    return await service.create(entity)


@pytest.mark.asyncio
class TestSubtaskEdgeRoundTrip:
    """The HAS_SUBTASK edge must be real and visible to the hierarchy readers."""

    async def test_subtask_is_visible_to_the_children_reader(
        self, tasks_service, test_user_uid
    ) -> None:
        """``get_subtasks`` — what ``GET /api/tasks/children`` calls — must find it.

        This is the assertion the whole change exists for: before it, the route door set
        no property and wrote no edge, so this read returned an empty list for a subtask
        the API had just created.
        """
        parent = await _route_create(tasks_service, task_request(), "task:rt-parent", test_user_uid)
        assert parent.is_ok, f"parent create failed: {parent.error}"

        child = await _route_create(
            tasks_service,
            task_request(title="Subtask", parent_uid=parent.value.uid),
            "task:rt-child",
            test_user_uid,
        )
        assert child.is_ok, f"subtask create failed: {child.error}"

        children = await tasks_service.get_subentities(parent.value.uid)
        assert children.is_ok, f"get_subtasks failed: {children.error}"
        assert [t.uid for t in children.value] == [child.value.uid], (
            "the parent's children read is empty — a task created through the generated "
            "CRUD route reached the graph with no parent at all"
        )

    async def test_parent_reader_resolves_the_other_way(self, tasks_service, test_user_uid) -> None:
        """``get_parent_task`` traverses the INVERSE edge, written in the same MERGE.

        Asserting only the forward direction would pass against a create that wrote
        HAS_SUBTASK and skipped SUBTASK_OF, leaving ``/api/tasks/parent`` broken.
        """
        parent = await _route_create(
            tasks_service, task_request(), "task:rt-parent2", test_user_uid
        )
        child = await _route_create(
            tasks_service,
            task_request(title="Subtask", parent_uid=parent.value.uid),
            "task:rt-child2",
            test_user_uid,
        )

        found = await tasks_service.get_parent_entity(child.value.uid)
        assert found.is_ok, f"get_parent_task failed: {found.error}"
        assert found.value is not None, "the subtask has no parent via SUBTASK_OF"
        assert found.value.uid == parent.value.uid

    async def test_the_uid_is_not_also_a_node_property(
        self, tasks_service, neo4j_driver, test_user_uid
    ) -> None:
        """The edge REPLACES the property. A denormalized copy would drift on re-parent —
        ``POST /api/tasks/add-child`` moves the edge and would never touch a property."""
        parent = await _route_create(
            tasks_service, task_request(), "task:rt-parent3", test_user_uid
        )
        child = await _route_create(
            tasks_service,
            task_request(title="Subtask", parent_uid=parent.value.uid),
            "task:rt-child3",
            test_user_uid,
        )

        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (t {uid: $uid}) RETURN t.parent_uid AS parent_uid", uid=child.value.uid
            )
            row = await result.single()

        assert row is not None
        assert row["parent_uid"] is None

    async def test_progress_weight_persists_on_the_edge(
        self, tasks_service, neo4j_driver, test_user_uid
    ) -> None:
        """``progress_weight`` is an EDGE property, and Tasks is the one domain that
        actually READS it back — ``calculate_parent_progress`` weights subtask completion
        by it, so a lost weight silently changes every parent's reported progress."""
        parent = await _route_create(
            tasks_service, task_request(), "task:rt-parent4", test_user_uid
        )
        child = await tasks_service.create_task(
            task_request(
                title="Quarter-weight subtask", parent_uid=parent.value.uid, progress_weight=0.25
            ),
            test_user_uid,
        )
        assert child.is_ok, f"subtask create failed: {child.error}"

        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (p {uid: $parent})-[r:HAS_SUBTASK]->(c {uid: $child}) "
                "RETURN r.progress_weight AS weight",
                parent=parent.value.uid,
                child=child.value.uid,
            )
            row = await result.single()

        assert row is not None, "no HAS_SUBTASK edge between the two tasks"
        assert row["weight"] == 0.25

    async def test_the_route_door_default_weight_reaches_the_edge(
        self, tasks_service, neo4j_driver, test_user_uid
    ) -> None:
        """The entity door has no weight to pass. Its default must land on the edge, or
        ``calculate_parent_progress`` reads a null and weights the subtask as zero."""
        parent = await _route_create(
            tasks_service, task_request(), "task:rt-parent5", test_user_uid
        )
        child = await _route_create(
            tasks_service,
            task_request(title="Subtask", parent_uid=parent.value.uid),
            "task:rt-child5",
            test_user_uid,
        )

        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (p {uid: $parent})-[r:HAS_SUBTASK]->(c {uid: $child}) "
                "RETURN r.progress_weight AS weight",
                parent=parent.value.uid,
                child=child.value.uid,
            )
            row = await result.single()

        assert row is not None, "no HAS_SUBTASK edge between the two tasks"
        assert row["weight"] == TaskCreateRequest.model_fields["progress_weight"].default

    async def test_another_users_task_cannot_become_a_parent(
        self, tasks_service, neo4j_driver, test_user_uid
    ) -> None:
        """A cross-user HAS_SUBTASK edge must never reach the graph.

        ``parent_uid`` is request input and the hierarchy backend matches on UID and label
        alone. The victim's context rebuild starts from the tasks they OWN and traverses
        HAS_SUBTASK without filtering the child's owner, so this edge would inject the
        attacker's task into the victim's cached context.

        Through ``create_task``, NOT the route door: the route door wrote no HAS_SUBTASK
        edge at all before this change, so a route-door version of this test would have
        passed against the unguarded code and proved nothing. ``create_task`` is the door
        that was writing this edge with no owner check.
        """
        async with neo4j_driver.session() as session:
            await session.run(
                "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()",
                uid=OTHER_USER,
            )
        await _create_node(
            neo4j_driver, "task:victims", "Task:Entity", "task", "Victim's task", OTHER_USER
        )

        child = await tasks_service.create_task(
            task_request(title="Attacker subtask", parent_uid="task:victims"), test_user_uid
        )

        assert child.is_ok, "the task itself is the caller's own and must still be created"
        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (p {uid: 'task:victims'})-[r:HAS_SUBTASK]->(c {uid: $child}) "
                "RETURN count(r) AS edges",
                child=child.value.uid,
            )
            row = await result.single()

        assert row["edges"] == 0, "a cross-user HAS_SUBTASK edge reached the graph"


@pytest.mark.asyncio
class TestHabitEdgeRoundTrip:
    """REINFORCES_HABIT must be a real edge, and the uid must not be a node property."""

    async def test_the_edge_is_written_and_correctly_oriented(
        self, tasks_service, neo4j_driver, test_user_uid
    ) -> None:
        await _create_node(
            neo4j_driver, "habit:rt", "Habit:Entity", "habit", "Morning pages", test_user_uid
        )

        task = await _route_create(
            tasks_service,
            task_request(reinforces_habit_uid="habit:rt"),
            "task:rt-habit",
            test_user_uid,
        )
        assert task.is_ok, f"create failed: {task.error}"

        async with neo4j_driver.session() as session:
            result = await session.run(
                f"MATCH (t {{uid: $task}})-[:{RelationshipName.REINFORCES_HABIT.value}]->"
                "(h {uid: 'habit:rt'}) RETURN count(*) AS edges",
                task=task.value.uid,
            )
            row = await result.single()

        assert row["edges"] == 1, (
            "no REINFORCES_HABIT edge — the generated CRUD route wrote the uid as a node "
            "property instead, which no reader consults"
        )

    async def test_the_uid_is_not_a_node_property(
        self, tasks_service, neo4j_driver, test_user_uid
    ) -> None:
        """The defect itself, asserted against the real serializer.

        The model documents this field as edge-backed; the claim rested on its absence
        from ``TaskDTO``, and this door persists the ENTITY.
        """
        await _create_node(
            neo4j_driver, "habit:rt2", "Habit:Entity", "habit", "Morning pages", test_user_uid
        )

        task = await _route_create(
            tasks_service,
            task_request(reinforces_habit_uid="habit:rt2"),
            "task:rt-habit2",
            test_user_uid,
        )

        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (t {uid: $uid}) RETURN t.reinforces_habit_uid AS habit_uid",
                uid=task.value.uid,
            )
            row = await result.single()

        assert row is not None
        assert row["habit_uid"] is None, "reinforces_habit_uid persisted as a node property"

    async def test_another_users_habit_is_refused(
        self, tasks_service, neo4j_driver, test_user_uid
    ) -> None:
        """Through ``create_task`` for the same reason as the cross-user parent above: the
        route door wrote no habit edge at all before this change, so it cannot RED-prove
        an admission guard. ``create_task`` wrote this edge straight from the request."""
        async with neo4j_driver.session() as session:
            await session.run(
                "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()",
                uid=OTHER_USER,
            )
        await _create_node(
            neo4j_driver, "habit:victims", "Habit:Entity", "habit", "Victim's habit", OTHER_USER
        )

        task = await tasks_service.create_task(
            task_request(reinforces_habit_uid="habit:victims"), test_user_uid
        )

        assert task.is_ok
        async with neo4j_driver.session() as session:
            result = await session.run(
                f"MATCH (t {{uid: $task}})-[r:{RelationshipName.REINFORCES_HABIT.value}]->() "
                "RETURN count(r) AS edges",
                task=task.value.uid,
            )
            row = await result.single()

        assert row["edges"] == 0, "a cross-user REINFORCES_HABIT edge reached the graph"

    async def test_a_non_habit_target_is_refused(
        self, tasks_service, neo4j_driver, test_user_uid
    ) -> None:
        """The field name declares the kind; the registry cannot — its Task-side
        REINFORCES_HABIT spec declares the target label as ``Entity``, so a same-user Goal
        UID would validate and then report a Goal under the task's habit context.

        Through ``create_task``, for the same RED-proof reason as the two guards above."""
        await _create_node(
            neo4j_driver, "goal:not-a-habit", "Goal:Entity", "goal", "A goal", test_user_uid
        )

        task = await tasks_service.create_task(
            task_request(reinforces_habit_uid="goal:not-a-habit"), test_user_uid
        )

        assert task.is_ok
        async with neo4j_driver.session() as session:
            result = await session.run(
                f"MATCH (t {{uid: $task}})-[r:{RelationshipName.REINFORCES_HABIT.value}]->() "
                "RETURN count(r) AS edges",
                task=task.value.uid,
            )
            row = await result.single()

        assert row["edges"] == 0, "a Goal was linked as the task's reinforced habit"


@pytest.mark.asyncio
class TestKnowledgeLinksStillWork:
    """The request door's knowledge lists went behind the same guard — the control that
    proves the guard did not simply close the door."""

    async def test_unowned_knowledge_is_still_linkable(
        self, tasks_service, neo4j_driver, test_user_uid
    ) -> None:
        """A Ku carries no owner, and "owned by nobody" must mean ALLOWED — a blunt
        "every endpoint must be mine" rule would break every knowledge list."""
        await _create_node(neo4j_driver, "ku.rt.one", "Ku:Entity", "ku", "Decorators")

        task = await tasks_service.create_task(
            task_request(applies_knowledge_uids=["ku.rt.one"]), test_user_uid
        )
        assert task.is_ok, f"create_task failed: {task.error}"

        async with neo4j_driver.session() as session:
            result = await session.run(
                f"MATCH (t {{uid: $task}})-[:{RelationshipName.APPLIES_KNOWLEDGE.value}]->"
                "(k {uid: 'ku.rt.one'}) RETURN count(*) AS edges",
                task=task.value.uid,
            )
            row = await result.single()

        assert row["edges"] == 1, "the admission guard refused an unowned Ku"

    async def test_a_dangling_uid_does_not_lose_the_valid_link(
        self, tasks_service, neo4j_driver, test_user_uid
    ) -> None:
        """Not an attack — a Ku deleted since the form was rendered does this. The batch
        is all-or-nothing and its failure is logged rather than propagated, so without the
        existence check one stale UID silently discards every valid link while the create
        still reports success."""
        await _create_node(neo4j_driver, "ku.rt.two", "Ku:Entity", "ku", "Generators")

        task = await tasks_service.create_task(
            task_request(applies_knowledge_uids=["ku.rt.two", "ku.rt.gone"]), test_user_uid
        )
        assert task.is_ok

        async with neo4j_driver.session() as session:
            result = await session.run(
                f"MATCH (t {{uid: $task}})-[:{RelationshipName.APPLIES_KNOWLEDGE.value}]->(k) "
                "RETURN collect(k.uid) AS uids",
                task=task.value.uid,
            )
            row = await result.single()

        assert row["uids"] == ["ku.rt.two"]


async def _goal_edge_targets(neo4j_driver, task_uid: str) -> list[str]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            f"MATCH (t {{uid: $task}})-[:{RelationshipName.FULFILLS_GOAL.value}]->(g) "
            "RETURN collect(g.uid) AS uids",
            task=task_uid,
        )
        row = await result.single()
    return row["uids"]


async def _goal_property(neo4j_driver, task_uid: str):
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (t {uid: $uid}) RETURN t.fulfills_goal_uid AS goal", uid=task_uid
        )
        row = await result.single()
    assert row is not None, f"task {task_uid} was not persisted"
    return row["goal"]


@pytest.mark.asyncio
class TestGoalEdgeRoundTrip:
    """``fulfills_goal_uid`` is dual-written: the node PROPERTY and the FULFILLS_GOAL EDGE,
    and the two must name the same goal.

    The property alone satisfied only the readers that hold the task in hand (relevance
    scoring, the completion → goal-progress cascade, the picker). Every goal-side reader
    traverses the edge — the open-task count that gates ``cancel_goal``, the goals-for-tasks
    batch the daily planner uses, the MEGA-QUERY's ``goal_context`` — so an app-created
    task was invisible to all of them. Both readers are exercised here directly, not
    simulated with a hand-written MATCH.
    """

    @pytest_asyncio.fixture
    async def cross_domain(self, neo4j_driver):
        return CrossDomainQueryService(CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver)))

    async def test_the_edge_and_the_property_name_the_same_goal(
        self, tasks_service, neo4j_driver, test_user_uid
    ) -> None:
        await _create_node(neo4j_driver, "goal:rt", "Goal:Entity", "goal", "Ship v1", test_user_uid)

        task = await tasks_service.create_task(
            task_request(fulfills_goal_uid="goal:rt"), test_user_uid
        )
        assert task.is_ok, f"create_task failed: {task.error}"

        assert await _goal_edge_targets(neo4j_driver, task.value.uid) == ["goal:rt"], (
            "no FULFILLS_GOAL edge — the request door wrote the property and nothing else"
        )
        assert await _goal_property(neo4j_driver, task.value.uid) == "goal:rt"
        assert task.value.fulfills_goal_uid == "goal:rt"

    async def test_the_goal_readers_see_the_task(
        self, tasks_service, cross_domain, neo4j_driver, test_user_uid
    ) -> None:
        """The two edge readers that were empty for every app-created task: the active
        open-task count (``GoalsService.cancel_goal``'s abandonment guard) and the
        goals-for-tasks batch (``TasksPlanningService`` dependency context)."""
        await _create_node(
            neo4j_driver, "goal:rt2", "Goal:Entity", "goal", "Ship v2", test_user_uid
        )

        task = await tasks_service.create_task(
            task_request(fulfills_goal_uid="goal:rt2", status=EntityStatus.ACTIVE), test_user_uid
        )
        assert task.is_ok, f"create_task failed: {task.error}"

        count = await cross_domain.count_active_tasks_for_goal("goal:rt2")
        assert count.is_ok, f"count_active_tasks_for_goal failed: {count.error}"
        assert count.value.count == 1, (
            "the goal's open-task count is 0 for a task that names it — the count reads "
            "FULFILLS_GOAL, and no edge was written"
        )

        goals = await cross_domain.get_goals_for_tasks_batch([task.value.uid])
        assert goals.is_ok, f"get_goals_for_tasks_batch failed: {goals.error}"
        assert [g.uid for g in goals.value.get(task.value.uid, ())] == ["goal:rt2"]

    async def test_entity_door_writes_the_edge_too(
        self, tasks_service, neo4j_driver, test_user_uid
    ) -> None:
        """The field rides on the Task, so the shared primitive writes it for BOTH doors."""
        await _create_node(
            neo4j_driver, "goal:rt3", "Goal:Entity", "goal", "Ship v3", test_user_uid
        )

        task = await _route_create(
            tasks_service, task_request(fulfills_goal_uid="goal:rt3"), "task:rt-goal", test_user_uid
        )
        assert task.is_ok, f"create failed: {task.error}"

        assert await _goal_edge_targets(neo4j_driver, "task:rt-goal") == ["goal:rt3"]
        assert await _goal_property(neo4j_driver, "task:rt-goal") == "goal:rt3"

    async def test_another_users_goal_is_refused_and_the_stamp_is_cleared(
        self, tasks_service, cross_domain, neo4j_driver, test_user_uid
    ) -> None:
        """Goals are OWNER_ONLY, and the goal readers do not filter the task's owner: a
        cross-user edge would count the attacker's task in the victim's goal progress. The
        edge is refused — and the property is cleared with it, so neither the node nor the
        returned task names a goal the graph does not connect."""
        async with neo4j_driver.session() as session:
            await session.run(
                "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()",
                uid=OTHER_USER,
            )
        await _create_node(
            neo4j_driver, "goal:victims", "Goal:Entity", "goal", "Victim's goal", OTHER_USER
        )

        task = await tasks_service.create_task(
            task_request(fulfills_goal_uid="goal:victims", status=EntityStatus.ACTIVE),
            test_user_uid,
        )
        assert task.is_ok, "the attacker's own task is legitimate and is created"

        assert await _goal_edge_targets(neo4j_driver, task.value.uid) == [], (
            "a cross-user FULFILLS_GOAL edge reached the graph"
        )
        assert await _goal_property(neo4j_driver, task.value.uid) is None, (
            "the refused goal is still stamped on the node — property and edge disagree"
        )
        assert task.value.fulfills_goal_uid is None

        count = await cross_domain.count_active_tasks_for_goal("goal:victims")
        assert count.is_ok and count.value.count == 0, (
            "the victim's open-task count exposes the attacker's task"
        )

    async def test_a_dangling_goal_uid_is_cleared(
        self, tasks_service, neo4j_driver, test_user_uid
    ) -> None:
        """Not an attack — a goal deleted since the form rendered, or a DSL ``@link`` typo.
        The property would satisfy no reader anyway; clearing keeps the halves agreeing."""
        task = await tasks_service.create_task(
            task_request(fulfills_goal_uid="goal:gone"), test_user_uid
        )
        assert task.is_ok

        assert await _goal_edge_targets(neo4j_driver, task.value.uid) == []
        assert await _goal_property(neo4j_driver, task.value.uid) is None
        assert task.value.fulfills_goal_uid is None

    async def test_a_non_goal_target_is_refused(
        self, tasks_service, neo4j_driver, test_user_uid
    ) -> None:
        """The field name declares the kind; a same-user Habit UID must not become the
        goal the task fulfills."""
        await _create_node(
            neo4j_driver, "habit:not-a-goal", "Habit:Entity", "habit", "A habit", test_user_uid
        )

        task = await tasks_service.create_task(
            task_request(fulfills_goal_uid="habit:not-a-goal"), test_user_uid
        )
        assert task.is_ok

        assert await _goal_edge_targets(neo4j_driver, task.value.uid) == []
        assert await _goal_property(neo4j_driver, task.value.uid) is None
