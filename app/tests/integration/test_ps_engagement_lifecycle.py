# mypy: disable-error-code="var-annotated"
"""Integration tests for ``PsEngagementService`` (Phase 4 verification).

Covers the four-transition lifecycle end-to-end against a real Neo4j
testcontainer:

    publish_pathstep    — T1 (validate + flip status)
    engage_pathstep     — T2 (spawn 6 instances + open ENGAGED_WITH edge)
    complete_pathstep   — T3 (mixed keep/discard review)
    abandon_pathstep    — T4 (delete all instances, preserve audit edge)

Plus the cross-transition invariants the unit tests can't reach:

- At-most-one-active engagement per (student, PS).
- Concurrent-engage exclusion.
- Validation report on broken cross-template refs.
- Empty-PS rejection.
- Partial-spawn rollback (covered indirectly by the validator gate before
  spawn — a true mid-spawn failure would need a fault-injecting backend).

The unit tests (``tests/unit/services/ps_engagement/``) cover the validator
and spawn-builder pure functions in isolation. This file is the only place
the four transitions are wired together against the real backends.

See:
    project_pathstep_lifecycle_contract.md (memory)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.ps_engagement_backend import PsEngagementBackend
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.choice.choice import Choice
from core.models.enums.entity_enums import EntityStatus
from core.models.enums.neo_labels import NeoLabel
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.pathways.path_step import PathStep
from core.models.principle.principle import Principle
from core.models.task.task import Task
from core.models.templates.choice_template import ChoiceTemplate
from core.models.templates.event_template import EventTemplate
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.habit_template import HabitTemplate
from core.models.templates.principle_template import PrincipleTemplate
from core.models.templates.relative_offset import RelativeOffset
from core.models.templates.task_template import TaskTemplate
from core.services.ps_engagement import PsEngagementService
from core.utils.result_simplified import Errors, Result

STUDENT_UID = "user_test_ps_engagement"
PS_UID = "ps_test_engagement"


# ============================================================================
# Stub PsService — PsEngagementService only calls .core.get(ps_uid)
# ============================================================================


class _StubPsCore:
    """Minimal core sub-service: just enough surface to satisfy publish_pathstep."""

    def __init__(self, backend: Any) -> None:
        self._backend = backend

    async def get(self, uid: str) -> Result[PathStep]:
        result = await self._backend.get(uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            return Result.fail(Errors.not_found("PathStep", uid))
        return result


class _StubPsService:
    """Stand-in for PsService — wraps a PS backend behind a ``.core`` attribute.

    PsEngagementService.publish_pathstep only calls ``self._ps_service.core.get()``.
    Wiring the full PsService (12 sub-services) is unnecessary overhead for
    these tests and would couple them to unrelated curriculum services.
    """

    def __init__(self, backend: Any) -> None:
        self.core = _StubPsCore(backend)


# ============================================================================
# Backends + service fixture
# ============================================================================


@pytest_asyncio.fixture
async def ps_backend(neo4j_driver, clean_neo4j):
    return UniversalNeo4jBackend[PathStep](
        neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY
    )


@pytest_asyncio.fixture
async def template_backends(neo4j_driver, clean_neo4j) -> dict[str, Any]:
    return {
        "task": UniversalNeo4jBackend[TaskTemplate](
            neo4j_driver, NeoLabel.TASK_TEMPLATE, TaskTemplate, base_label=NeoLabel.ENTITY
        ),
        "goal": UniversalNeo4jBackend[GoalTemplate](
            neo4j_driver, NeoLabel.GOAL_TEMPLATE, GoalTemplate, base_label=NeoLabel.ENTITY
        ),
        "habit": UniversalNeo4jBackend[HabitTemplate](
            neo4j_driver, NeoLabel.HABIT_TEMPLATE, HabitTemplate, base_label=NeoLabel.ENTITY
        ),
        "event": UniversalNeo4jBackend[EventTemplate](
            neo4j_driver, NeoLabel.EVENT_TEMPLATE, EventTemplate, base_label=NeoLabel.ENTITY
        ),
        "choice": UniversalNeo4jBackend[ChoiceTemplate](
            neo4j_driver, NeoLabel.CHOICE_TEMPLATE, ChoiceTemplate, base_label=NeoLabel.ENTITY
        ),
        "principle": UniversalNeo4jBackend[PrincipleTemplate](
            neo4j_driver,
            NeoLabel.PRINCIPLE_TEMPLATE,
            PrincipleTemplate,
            base_label=NeoLabel.ENTITY,
        ),
    }


@pytest_asyncio.fixture
async def instance_backends(neo4j_driver, clean_neo4j) -> dict[str, Any]:
    return {
        "tasks": UniversalNeo4jBackend[Task](
            neo4j_driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY
        ),
        "goals": UniversalNeo4jBackend[Goal](
            neo4j_driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY
        ),
        "habits": UniversalNeo4jBackend[Habit](
            neo4j_driver, NeoLabel.HABIT, Habit, base_label=NeoLabel.ENTITY
        ),
        "events": UniversalNeo4jBackend[Event](
            neo4j_driver, NeoLabel.EVENT, Event, base_label=NeoLabel.ENTITY
        ),
        "choices": UniversalNeo4jBackend[Choice](
            neo4j_driver, NeoLabel.CHOICE, Choice, base_label=NeoLabel.ENTITY
        ),
        "principles": UniversalNeo4jBackend[Principle](
            neo4j_driver, NeoLabel.PRINCIPLE, Principle, base_label=NeoLabel.ENTITY
        ),
    }


@pytest_asyncio.fixture
async def executor(neo4j_driver) -> Neo4jQueryExecutor:
    return Neo4jQueryExecutor(neo4j_driver)


@pytest_asyncio.fixture
async def engagement_service(
    executor: Neo4jQueryExecutor,
    ps_backend: Any,
    template_backends: dict[str, Any],
    instance_backends: dict[str, Any],
) -> PsEngagementService:
    return PsEngagementService(
        backend=PsEngagementBackend(executor),
        ps_service=_StubPsService(ps_backend),
        task_template_backend=template_backends["task"],
        goal_template_backend=template_backends["goal"],
        habit_template_backend=template_backends["habit"],
        event_template_backend=template_backends["event"],
        choice_template_backend=template_backends["choice"],
        principle_template_backend=template_backends["principle"],
        tasks_backend=instance_backends["tasks"],
        goals_backend=instance_backends["goals"],
        habits_backend=instance_backends["habits"],
        events_backend=instance_backends["events"],
        choices_backend=instance_backends["choices"],
        principles_backend=instance_backends["principles"],
    )


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    """Create the test student User node and clean it up afterwards.

    The session-scoped ``ensure_test_users`` fixture in conftest covers a
    fixed allowlist of test UIDs; STUDENT_UID is specific to this file so
    we own its lifecycle here.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) ON CREATE SET u.title = $uid, u.created_at = datetime($ts)",
            uid=STUDENT_UID,
            ts=datetime.now(UTC).isoformat(),
        )
    yield STUDENT_UID
    async with neo4j_driver.session() as session:
        await session.run("MATCH (u:User {uid: $uid}) DETACH DELETE u", uid=STUDENT_UID)


# ============================================================================
# Helpers — build a PS with templates + edges in one call
# ============================================================================


async def _attach_template(
    executor: Neo4jQueryExecutor, ps_uid: str, template_uid: str, edge: str
) -> None:
    """MERGE a HAS_*_TEMPLATE edge between an existing PS and template."""
    res = await executor.execute_write(
        query=(f"MATCH (ps {{uid: $ps}}), (t {{uid: $t}}) MERGE (ps)-[r:{edge}]->(t) RETURN r"),
        params={"ps": ps_uid, "t": template_uid},
        operation="attach_template",
    )
    assert res.is_ok, f"failed to attach {edge}: {res.expect_error()}"


async def _seed_full_bundle(
    ps_backend: Any,
    template_backends: dict[str, Any],
    executor: Neo4jQueryExecutor,
    *,
    cross_refs: bool = False,
) -> dict[str, str]:
    """Create a PS plus one template per domain, attach all 6 edges.

    Returns a dict of ``{"ps": ..., "task": ..., "goal": ..., ...}`` with the
    UIDs the caller needs for later assertions.
    """
    uids = {
        "ps": PS_UID,
        "task": "ttpl_test",
        "goal": "gtpl_test",
        "habit": "htpl_test",
        "event": "etpl_test",
        "choice": "ctpl_test",
        "principle": "ptpl_test",
    }

    ps = PathStep(uid=uids["ps"], title="Test PathStep")
    assert (await ps_backend.create(ps)).is_ok

    # Build the 6 templates. When cross_refs=True the Task and Goal templates
    # carry valid forward references to other templates in the same PS so we
    # can verify reference resolution at spawn time.
    if cross_refs:
        task = TaskTemplate(
            uid=uids["task"],
            title="Practice problem",
            status=EntityStatus.ACTIVE,
            due_offset=RelativeOffset(days=7),
            fulfills_goal_template_uid=uids["goal"],
            reinforces_habit_template_uid=uids["habit"],
        )
        goal = GoalTemplate(
            uid=uids["goal"],
            title="Master the topic",
            status=EntityStatus.ACTIVE,
            target_offset=RelativeOffset(days=30),
            inspired_by_choice_template_uid=uids["choice"],
        )
    else:
        task = TaskTemplate(
            uid=uids["task"],
            title="Practice problem",
            status=EntityStatus.ACTIVE,
            due_offset=RelativeOffset(days=7),
        )
        goal = GoalTemplate(
            uid=uids["goal"],
            title="Master the topic",
            status=EntityStatus.ACTIVE,
            target_offset=RelativeOffset(days=30),
        )

    habit = HabitTemplate(uid=uids["habit"], title="Daily review", status=EntityStatus.ACTIVE)
    event = EventTemplate(
        uid=uids["event"],
        title="Cohort kickoff",
        status=EntityStatus.ACTIVE,
        event_offset=RelativeOffset(days=1),
        # When cross_refs, the event reinforces the habit (→ REINFORCES_HABIT edge).
        reinforces_habit_template_uid=uids["habit"] if cross_refs else None,
    )
    choice = ChoiceTemplate(uid=uids["choice"], title="Track selection", status=EntityStatus.ACTIVE)
    principle = PrincipleTemplate(
        uid=uids["principle"], title="Practice over theory", status=EntityStatus.ACTIVE
    )

    assert (await template_backends["task"].create(task)).is_ok
    assert (await template_backends["goal"].create(goal)).is_ok
    assert (await template_backends["habit"].create(habit)).is_ok
    assert (await template_backends["event"].create(event)).is_ok
    assert (await template_backends["choice"].create(choice)).is_ok
    assert (await template_backends["principle"].create(principle)).is_ok

    await _attach_template(executor, uids["ps"], uids["task"], "HAS_TASK_TEMPLATE")
    await _attach_template(executor, uids["ps"], uids["goal"], "HAS_GOAL_TEMPLATE")
    await _attach_template(executor, uids["ps"], uids["habit"], "HAS_HABIT_TEMPLATE")
    await _attach_template(executor, uids["ps"], uids["event"], "HAS_EVENT_TEMPLATE")
    await _attach_template(executor, uids["ps"], uids["choice"], "HAS_CHOICE_TEMPLATE")
    await _attach_template(executor, uids["ps"], uids["principle"], "HAS_PRINCIPLE_TEMPLATE")

    return uids


async def _engagement_state(executor: Neo4jQueryExecutor, student: str, ps: str) -> str | None:
    """Return the ENGAGED_WITH edge state, or None if no edge exists."""
    res = await executor.execute(
        query=(
            "MATCH (u:User {uid: $student})-[r:ENGAGED_WITH]->(ps {uid: $ps}) "
            "RETURN r.state AS state"
        ),
        params={"student": student, "ps": ps},
        operation="check_engagement",
    )
    assert res.is_ok
    return res.value[0]["state"] if res.value else None


async def _instance_count(executor: Neo4jQueryExecutor, student: str, ps: str) -> int:
    """Count engaged-or-owned instances spawned by the (student, PS) engagement."""
    res = await executor.execute(
        query=(
            "MATCH (ps {uid: $ps})-[:HAS_TASK_TEMPLATE|HAS_GOAL_TEMPLATE"
            "|HAS_HABIT_TEMPLATE|HAS_EVENT_TEMPLATE|HAS_CHOICE_TEMPLATE"
            "|HAS_PRINCIPLE_TEMPLATE]->(t) "
            "MATCH (n {user_uid: $student})-[:SPAWNED_FROM]->(t) "
            "RETURN count(n) AS n"
        ),
        params={"student": student, "ps": ps},
        operation="count_instances",
    )
    assert res.is_ok
    return int(res.value[0]["n"]) if res.value else 0


# ============================================================================
# T1 — Publish
# ============================================================================


@pytest.mark.asyncio
class TestPublishPathStep:
    async def test_publish_succeeds_for_valid_bundle(
        self, engagement_service, ps_backend, template_backends, executor
    ):
        await _seed_full_bundle(ps_backend, template_backends, executor)

        result = await engagement_service.publish_pathstep(PS_UID)

        assert result.is_ok, f"publish failed: {result.expect_error()}"
        ps = result.value
        assert ps.uid == PS_UID

        # Status was flipped — read it back via raw Cypher to bypass any
        # interpretation in PathStep's __post_init__.
        status_res = await executor.execute(
            query="MATCH (ps {uid: $uid}) RETURN ps.status AS status",
            params={"uid": PS_UID},
            operation="check_status",
        )
        assert status_res.is_ok
        assert status_res.value[0]["status"] == "published"

    async def test_publish_returns_validation_report_for_missing_target(
        self, engagement_service, ps_backend, template_backends, executor
    ):
        # Build a PS whose Task template references a non-existent goal.
        ps = PathStep(uid=PS_UID, title="Broken PS")
        await ps_backend.create(ps)
        bad_task = TaskTemplate(
            uid="ttpl_bad",
            title="Task with broken ref",
            status=EntityStatus.ACTIVE,
            fulfills_goal_template_uid="gtpl_does_not_exist",
        )
        await template_backends["task"].create(bad_task)
        await _attach_template(executor, PS_UID, "ttpl_bad", "HAS_TASK_TEMPLATE")

        result = await engagement_service.publish_pathstep(PS_UID)

        assert result.is_error
        err = result.expect_error()
        assert err.details["rule"] == "ps_template_validation"
        violations = err.details["violations"]
        assert len(violations) == 1
        v = violations[0]
        assert v["violation"] == "target_missing"
        assert v["field"] == "fulfills_goal_template_uid"
        assert v["referenced_uid"] == "gtpl_does_not_exist"
        assert v["template_type"] == "TaskTemplate"

    async def test_publish_fails_for_missing_pathstep(self, engagement_service):
        result = await engagement_service.publish_pathstep("ps_does_not_exist")

        assert result.is_error
        # Loader walks 6 HAS_*_TEMPLATE edges — non-existent PS yields an
        # empty bundle (loader returns ok), and validation passes (empty is
        # valid). The status update then fails with not_found.
        assert result.expect_error().category.name in {"NOT_FOUND", "BUSINESS"}


# ============================================================================
# T2 — Engage
# ============================================================================


@pytest.mark.asyncio
class TestEngagePathStep:
    async def test_engage_spawns_one_instance_per_template(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        await _seed_full_bundle(ps_backend, template_backends, executor)

        result = await engagement_service.engage_pathstep(test_user, PS_UID)

        assert result.is_ok, f"engage failed: {result.expect_error()}"
        engagement = result.value
        assert engagement.state == "engaged"
        assert engagement.student_uid == test_user
        assert engagement.ps_uid == PS_UID
        assert len(engagement.spawned_instance_uids) == 6

        # Verify state on disk: 6 instances, all engaged, ENGAGED_WITH edge.
        assert await _instance_count(executor, test_user, PS_UID) == 6
        assert await _engagement_state(executor, test_user, PS_UID) == "engaged"

        # Every instance has a SPAWNED_FROM edge to its template
        # and carries engagement_state="engaged".
        states_res = await executor.execute(
            query=(
                "MATCH (ps {uid: $ps})-[:HAS_TASK_TEMPLATE|HAS_GOAL_TEMPLATE"
                "|HAS_HABIT_TEMPLATE|HAS_EVENT_TEMPLATE|HAS_CHOICE_TEMPLATE"
                "|HAS_PRINCIPLE_TEMPLATE]->(t) "
                "MATCH (n {user_uid: $student})-[:SPAWNED_FROM]->(t) "
                "RETURN n.engagement_state AS state, t.uid AS tpl"
            ),
            params={"ps": PS_UID, "student": test_user},
            operation="check_states",
        )
        assert states_res.is_ok
        assert len(states_res.value) == 6
        for record in states_res.value:
            assert record["state"] == "engaged"
            assert record["tpl"] is not None

    async def test_engage_resolves_cross_template_refs(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        uids = await _seed_full_bundle(ps_backend, template_backends, executor, cross_refs=True)

        result = await engagement_service.engage_pathstep(test_user, PS_UID)
        assert result.is_ok

        # Find the spawned task instance, check its fulfills_goal_uid points
        # at the spawned goal instance (NOT the template UID).
        ref_res = await executor.execute(
            query=(
                "MATCH (task {user_uid: $student})-[:SPAWNED_FROM]->(:Entity {uid: $task_tpl}) "
                "MATCH (goal {user_uid: $student})-[:SPAWNED_FROM]->(:Entity {uid: $goal_tpl}) "
                "RETURN task.fulfills_goal_uid AS goal_ref, "
                "       goal.uid AS goal_instance_uid"
            ),
            params={
                "student": test_user,
                "task_tpl": uids["task"],
                "goal_tpl": uids["goal"],
            },
            operation="check_refs",
        )
        assert ref_res.is_ok and ref_res.value
        record = ref_res.value[0]
        assert record["goal_ref"] == record["goal_instance_uid"]
        assert record["goal_ref"] != uids["goal"]  # rewritten away from template uid

        # Task → Habit linkage is a graph edge (REINFORCES_HABIT), not a property.
        task_habit_edge = await executor.execute(
            query=(
                "MATCH (task {user_uid: $student})-[:SPAWNED_FROM]->(:Entity {uid: $task_tpl}) "
                "MATCH (habit {user_uid: $student})-[:SPAWNED_FROM]->(:Entity {uid: $habit_tpl}) "
                "OPTIONAL MATCH (task)-[r:REINFORCES_HABIT]->(habit) "
                "RETURN r IS NOT NULL AS edge_exists"
            ),
            params={
                "student": test_user,
                "task_tpl": uids["task"],
                "habit_tpl": uids["habit"],
            },
            operation="check_reinforces_habit_edge",
        )
        assert task_habit_edge.is_ok and task_habit_edge.value
        assert task_habit_edge.value[0]["edge_exists"], (
            "Spawned Task must have (Task)-[:REINFORCES_HABIT]->(Habit) edge — "
            "see TASK_SPEC.cross_edges in _spawn_orchestrator.py"
        )

        # Goal → Choice linkage is a graph edge (INSPIRED_BY_CHOICE), not a property.
        # Verify the spawned goal has the edge to the spawned choice instance.
        edge_res = await executor.execute(
            query=(
                "MATCH (goal {user_uid: $student})-[:SPAWNED_FROM]->(:Entity {uid: $goal_tpl}) "
                "MATCH (choice {user_uid: $student})-[:SPAWNED_FROM]->(:Entity {uid: $choice_tpl}) "
                "OPTIONAL MATCH (goal)-[r:INSPIRED_BY_CHOICE]->(choice) "
                "RETURN r IS NOT NULL AS edge_exists"
            ),
            params={
                "student": test_user,
                "goal_tpl": uids["goal"],
                "choice_tpl": uids["choice"],
            },
            operation="check_inspired_by_choice_edge",
        )
        assert edge_res.is_ok and edge_res.value
        assert edge_res.value[0]["edge_exists"], (
            "Spawned Goal must have (Goal)-[:INSPIRED_BY_CHOICE]->(Choice) edge — "
            "see GOAL_SPEC.cross_edges in _spawn_orchestrator.py"
        )

    async def test_engage_fails_for_empty_pathstep(self, engagement_service, ps_backend, test_user):
        # PS exists but has no templates attached.
        await ps_backend.create(PathStep(uid=PS_UID, title="Empty PS"))

        result = await engagement_service.engage_pathstep(test_user, PS_UID)

        assert result.is_error
        err = result.expect_error()
        assert err.details["rule"] == "empty_pathstep"

    async def test_second_engage_blocked_by_active(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        await _seed_full_bundle(ps_backend, template_backends, executor)

        first = await engagement_service.engage_pathstep(test_user, PS_UID)
        assert first.is_ok

        second = await engagement_service.engage_pathstep(test_user, PS_UID)
        assert second.is_error
        assert second.expect_error().details["rule"] == "engagement_already_active"


# ============================================================================
# T3 — Complete (mixed keep/discard review)
# ============================================================================


@pytest.mark.asyncio
class TestCompletePathStep:
    async def test_complete_with_mixed_review(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        uids = await _seed_full_bundle(ps_backend, template_backends, executor)
        engage = await engagement_service.engage_pathstep(test_user, PS_UID)
        assert engage.is_ok
        assert await _instance_count(executor, test_user, PS_UID) == 6

        # Discard task + event; keep the rest (4 should remain).
        review = {
            uids["task"]: "discard",
            uids["event"]: "discard",
            uids["goal"]: "keep",
            uids["habit"]: "keep",
            uids["choice"]: "keep",
            uids["principle"]: "keep",
        }
        complete = await engagement_service.complete_pathstep(test_user, PS_UID, review)

        assert complete.is_ok, f"complete failed: {complete.expect_error()}"
        assert complete.value.state == "completed"

        # Engagement edge transitioned.
        assert await _engagement_state(executor, test_user, PS_UID) == "completed"

        # Two discards removed, four kept transitioned to 'owned'.
        kept = await executor.execute(
            query=(
                "MATCH (ps {uid: $ps})-[:HAS_TASK_TEMPLATE|HAS_GOAL_TEMPLATE"
                "|HAS_HABIT_TEMPLATE|HAS_EVENT_TEMPLATE|HAS_CHOICE_TEMPLATE"
                "|HAS_PRINCIPLE_TEMPLATE]->(t) "
                "MATCH (n {user_uid: $student})-[:SPAWNED_FROM]->(t) "
                "RETURN t.uid AS tpl, n.engagement_state AS state"
            ),
            params={"ps": PS_UID, "student": test_user},
            operation="check_post_complete",
        )
        assert kept.is_ok
        rows = {r["tpl"]: r["state"] for r in kept.value}
        assert uids["task"] not in rows
        assert uids["event"] not in rows
        assert rows[uids["goal"]] == "owned"
        assert rows[uids["habit"]] == "owned"
        assert rows[uids["choice"]] == "owned"
        assert rows[uids["principle"]] == "owned"

    async def test_complete_defaults_unspecified_templates_to_keep(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        uids = await _seed_full_bundle(ps_backend, template_backends, executor)
        await engagement_service.engage_pathstep(test_user, PS_UID)

        # Empty review = keep everything by default.
        complete = await engagement_service.complete_pathstep(test_user, PS_UID, {})
        assert complete.is_ok

        # All 6 instances should be 'owned' now.
        rows_res = await executor.execute(
            query=(
                "MATCH (ps {uid: $ps})-[:HAS_TASK_TEMPLATE|HAS_GOAL_TEMPLATE"
                "|HAS_HABIT_TEMPLATE|HAS_EVENT_TEMPLATE|HAS_CHOICE_TEMPLATE"
                "|HAS_PRINCIPLE_TEMPLATE]->(t) "
                "MATCH (n {user_uid: $student})-[:SPAWNED_FROM]->(t) "
                "RETURN n.engagement_state AS state"
            ),
            params={"ps": PS_UID, "student": test_user},
            operation="check_states_after_default_keep",
        )
        assert rows_res.is_ok
        assert len(rows_res.value) == 6
        assert all(r["state"] == "owned" for r in rows_res.value)
        assert uids["task"]  # touch to silence unused-var lint

    async def test_complete_fails_without_active_engagement(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        await _seed_full_bundle(ps_backend, template_backends, executor)

        # No engage call — complete should report the missing engagement.
        result = await engagement_service.complete_pathstep(test_user, PS_UID, {})

        assert result.is_error
        assert result.expect_error().category.name == "NOT_FOUND"


# ============================================================================
# T4 — Abandon
# ============================================================================


@pytest.mark.asyncio
class TestAbandonPathStep:
    async def test_abandon_deletes_all_instances(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        await _seed_full_bundle(ps_backend, template_backends, executor)
        await engagement_service.engage_pathstep(test_user, PS_UID)
        assert await _instance_count(executor, test_user, PS_UID) == 6

        result = await engagement_service.abandon_pathstep(test_user, PS_UID)

        assert result.is_ok
        assert result.value.state == "abandoned"

        # Every spawned instance gone.
        assert await _instance_count(executor, test_user, PS_UID) == 0

        # Edge preserved with state='abandoned' for audit.
        assert await _engagement_state(executor, test_user, PS_UID) == "abandoned"

    async def test_abandon_fails_without_active_engagement(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        await _seed_full_bundle(ps_backend, template_backends, executor)

        result = await engagement_service.abandon_pathstep(test_user, PS_UID)
        assert result.is_error
        assert result.expect_error().category.name == "NOT_FOUND"

    async def test_re_engage_after_abandon_succeeds(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        """Abandoned engagement edge is preserved but does not block re-engage."""
        await _seed_full_bundle(ps_backend, template_backends, executor)
        await engagement_service.engage_pathstep(test_user, PS_UID)
        await engagement_service.abandon_pathstep(test_user, PS_UID)

        re_engage = await engagement_service.engage_pathstep(test_user, PS_UID)

        assert re_engage.is_ok
        assert re_engage.value.state == "engaged"
        assert await _instance_count(executor, test_user, PS_UID) == 6

        # Two ENGAGED_WITH edges should exist now: the audited 'abandoned'
        # one and the fresh 'engaged' one.
        edge_count = await executor.execute(
            query=(
                "MATCH (u:User {uid: $student})-[r:ENGAGED_WITH]->(ps {uid: $ps}) "
                "RETURN r.state AS state ORDER BY r.state"
            ),
            params={"student": test_user, "ps": PS_UID},
            operation="check_edge_history",
        )
        assert edge_count.is_ok
        states = sorted(r["state"] for r in edge_count.value)
        assert states == ["abandoned", "engaged"]


# ============================================================================
# Concurrency — at-most-one-active invariant under racing engages
# ============================================================================


@pytest.mark.asyncio
class TestConcurrentEngage:
    async def test_simultaneous_engages_resolve_to_consistent_state(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        """Two concurrent engage calls — verify the invariant holds.

        Per ``_engagement_gateway.open_engagement`` the find_active→CREATE pair
        is not atomic, so V1 accepts the race. What we DO require:

        - At least one call returns ok.
        - The (student, PS) pair never ends up with stranded instances from
          a losing engagement (i.e. instance count is consistent with the
          number of successful engages).

        If both calls happen to win (cache miss + parallel CREATE) we'd see
        12 instances and two 'engaged' edges, which would still be correct
        relative to today's V1 contract — but the typical outcome on a
        single-driver session is one winner + one already-active error.
        """
        await _seed_full_bundle(ps_backend, template_backends, executor)

        results = await asyncio.gather(
            engagement_service.engage_pathstep(test_user, PS_UID),
            engagement_service.engage_pathstep(test_user, PS_UID),
            return_exceptions=False,
        )

        oks = [r for r in results if r.is_ok]
        errs = [r for r in results if r.is_error]

        # At least one must succeed.
        assert len(oks) >= 1, "no engage succeeded under concurrency"

        # Any failure must be the at-most-one-active business error — never
        # a database/system error (those would mean the gateway misbehaved).
        for err_result in errs:
            err = err_result.expect_error()
            assert err.details.get("rule") == "engagement_already_active", (
                f"unexpected failure category: {err}"
            )

        # Edge / instance counts are consistent with the number of winners.
        edges_res = await executor.execute(
            query=(
                "MATCH (u:User {uid: $student})-[r:ENGAGED_WITH]->(ps {uid: $ps}) "
                "WHERE r.state = 'engaged' RETURN count(r) AS n"
            ),
            params={"student": test_user, "ps": PS_UID},
            operation="count_active_edges",
        )
        assert edges_res.is_ok
        active_edges = int(edges_res.value[0]["n"])
        assert active_edges == len(oks)
        assert await _instance_count(executor, test_user, PS_UID) == 6 * len(oks)


# ============================================================================
# Round-trip back-references — spawn → discover → mutate → re-discover
# ============================================================================
#
# The four-transition tests above cover the engagement service's lifecycle
# contract (publish/engage/complete/abandon). These tests cover the *round
# trip* — the back-references that let a spawned activity be traced to its
# originating PathStep and engagement, plus the gaps where back-references
# are declared but not implemented.


@pytest.mark.asyncio
class TestRoundTripBackReferences:
    """Verify the graph-native back-reference: (instance)-[:SPAWNED_FROM]->(template).

    SKUEL committed to graph-native relationships for the spawn back-reference —
    no parallel ``template_uid`` property as denormalized cache. ``list_engaged``
    re-discovers spawned instances by traversing ``[:SPAWNED_FROM]`` to templates
    attached to each PS; ``UserContextBuilder`` then derives
    ``spawned_uid_to_ps_uid`` from those results.

    ``source_path_step_uid`` is a domain-model field on all six activity
    instances, and the spawn orchestrator now populates it uniformly. The
    field is load-bearing on the consumer side (``get_tasks_for_step``,
    adaptive-LP learning-task detection, habit/event planning) and is the
    only PS-back-reference for curriculum activities created *without* a
    template (no ``SPAWNED_FROM`` edge to traverse). The earlier Goal/Choice/
    Principle-only behaviour was an inconsistency, not a design — see
    ``test_spawned_source_path_step_uid_uniform_on_all_six``.
    """

    async def test_spawned_from_edge_set_on_all_six_instances(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        """Every spawned instance has a SPAWNED_FROM edge to its template.

        This is the universal back-reference — used by every engagement-discovery
        query and by the round-trip in ``list_engaged``. A missing edge would
        silently drop the instance from ``spawned_uid_to_ps_uid`` and from the
        engagement-bucketed daily plan.
        """
        uids = await _seed_full_bundle(ps_backend, template_backends, executor)
        engage = await engagement_service.engage_pathstep(test_user, PS_UID)
        assert engage.is_ok

        rows = await executor.execute(
            query=(
                "MATCH (n {user_uid: $student})-[r:SPAWNED_FROM]->(t) "
                "RETURN t.uid AS tpl, n.uid AS instance_uid, "
                "       r.spawned_at AS spawned_at"
            ),
            params={"student": test_user},
            operation="round_trip_spawned_from",
        )
        assert rows.is_ok
        assert len(rows.value) == 6
        template_uids_traversed = {r["tpl"] for r in rows.value}
        assert template_uids_traversed == {
            uids["task"],
            uids["goal"],
            uids["habit"],
            uids["event"],
            uids["choice"],
            uids["principle"],
        }
        # Every edge carries the spawned_at timestamp (set atomically with
        # node creation in create_with_spawned_from).
        for record in rows.value:
            assert record["spawned_at"] is not None, (
                f"SPAWNED_FROM edge for instance {record['instance_uid']} "
                "missing spawned_at — atomic create did not set it"
            )

    async def test_no_template_uid_property_remains_on_spawned_instances(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        """The ``template_uid`` property was dropped — only the edge remains.

        Guard against a regression where someone re-adds the property as a
        cache. SKUEL chose graph-native without the property; this test
        locks that choice in. If you intentionally re-add ``template_uid``
        as a denormalized cache (Forms pattern), delete this test and add
        one that asserts edge+property agreement.
        """
        await _seed_full_bundle(ps_backend, template_backends, executor)
        engage = await engagement_service.engage_pathstep(test_user, PS_UID)
        assert engage.is_ok

        rows = await executor.execute(
            query=(
                "MATCH (n)-[:SPAWNED_FROM]->(t) WHERE n.user_uid = $student "
                "RETURN n.template_uid AS prop_present"
            ),
            params={"student": test_user},
            operation="check_no_template_uid_property",
        )
        assert rows.is_ok
        for record in rows.value:
            assert record["prop_present"] is None, (
                "Found template_uid property on a spawned instance — "
                "the property was dropped in favour of the SPAWNED_FROM edge. "
                "See TestRoundTripBackReferences class docstring."
            )

    async def test_reinforces_habit_uid_never_persisted_on_task_node(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        """``Task.reinforces_habit_uid`` is a DERIVED field — never written to Neo4j.

        The Task↔Habit link is the (Task)-[:REINFORCES_HABIT]->(Habit) edge. The
        domain model carries a derived ``reinforces_habit_uid`` for in-memory
        scorers, but it must NEVER be persisted as a node property (that would
        recreate the drift we eliminated). This guard spawns a task that
        reinforces a habit (via cross_refs) and asserts the node has the edge but
        no property.
        """
        uids = await _seed_full_bundle(ps_backend, template_backends, executor, cross_refs=True)
        engage = await engagement_service.engage_pathstep(test_user, PS_UID)
        assert engage.is_ok

        rows = await executor.execute(
            query=(
                "MATCH (task {user_uid: $student})-[:SPAWNED_FROM]->(:Entity {uid: $task_tpl}) "
                "OPTIONAL MATCH (task)-[r:REINFORCES_HABIT]->(:Entity) "
                "RETURN task.reinforces_habit_uid AS prop_present, "
                "       count(r) AS edge_count"
            ),
            params={"student": test_user, "task_tpl": uids["task"]},
            operation="check_reinforces_habit_not_persisted",
        )
        assert rows.is_ok and rows.value
        record = rows.value[0]
        assert record["prop_present"] is None, (
            "Found reinforces_habit_uid property on a Task node — it is a DERIVED "
            "field and must never be persisted. The REINFORCES_HABIT edge is the "
            "single source of truth. See Task model field comment."
        )
        assert record["edge_count"] == 1, (
            "Spawned task should have exactly one REINFORCES_HABIT edge"
        )

    async def test_reinforces_habit_uid_never_persisted_on_event_node(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        """``Event.reinforces_habit_uid`` is a DERIVED field — never written to Neo4j.

        The Event↔Habit link is the (Event)-[:REINFORCES_HABIT]->(Habit) edge.
        Mirrors the Task guard above — the spawned event reinforces a habit (via
        cross_refs) and the node must carry the edge but no property.
        """
        uids = await _seed_full_bundle(ps_backend, template_backends, executor, cross_refs=True)
        engage = await engagement_service.engage_pathstep(test_user, PS_UID)
        assert engage.is_ok

        rows = await executor.execute(
            query=(
                "MATCH (event {user_uid: $student})-[:SPAWNED_FROM]->(:Entity {uid: $event_tpl}) "
                "OPTIONAL MATCH (event)-[r:REINFORCES_HABIT]->(:Entity) "
                "RETURN event.reinforces_habit_uid AS prop_present, "
                "       count(r) AS edge_count"
            ),
            params={"student": test_user, "event_tpl": uids["event"]},
            operation="check_event_reinforces_habit_not_persisted",
        )
        assert rows.is_ok and rows.value
        record = rows.value[0]
        assert record["prop_present"] is None, (
            "Found reinforces_habit_uid property on an Event node — it is a DERIVED "
            "field and must never be persisted. The REINFORCES_HABIT edge is the "
            "single source of truth. See Event model field comment."
        )
        assert record["edge_count"] == 1, (
            "Spawned event should have exactly one REINFORCES_HABIT edge"
        )

    async def test_spawned_source_path_step_uid_uniform_on_all_six(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        """The spawn orchestrator writes ``source_path_step_uid`` on all six instances.

        Previously only Goal/Choice/Principle carried it; Task/Habit/Event were
        left None, which made spawned tasks invisible to ``get_tasks_for_step``
        and starved the adaptive-LP / habit / event consumers that read the
        field. The PS-back-reference is now denormalised uniformly onto every
        spawned instance — symmetric with the field's presence on all six
        domain models and with the non-template scheduling-service paths that
        already set it. The ``SPAWNED_FROM`` edge remains the universal
        back-reference; this field is the directly-readable companion.
        """
        await _seed_full_bundle(ps_backend, template_backends, executor)
        engage = await engagement_service.engage_pathstep(test_user, PS_UID)
        assert engage.is_ok

        rows = await executor.execute(
            query=(
                "MATCH (n {user_uid: $student})-[:SPAWNED_FROM]->(t) "
                "RETURN labels(n) AS labs, n.source_path_step_uid AS src_ps"
            ),
            params={"student": test_user},
            operation="round_trip_source_ps",
        )
        assert rows.is_ok
        by_label: dict[str, str | None] = {}
        for record in rows.value:
            domain_label = next((lab for lab in record["labs"] if lab != "Entity"), "Entity")
            by_label[domain_label] = record["src_ps"]

        for label in ("Task", "Goal", "Habit", "Event", "Choice", "Principle"):
            assert by_label[label] == PS_UID, (
                f"{label} must carry source_path_step_uid={PS_UID} at spawn time "
                "— the spawn orchestrator populates it uniformly on all six instances"
            )

    async def test_list_engaged_round_trips_spawned_instance_uids(
        self, engagement_service, ps_backend, template_backends, executor, test_user
    ):
        """``list_engaged`` re-discovers the same instances the spawn just created.

        This is the path ``UserContextBuilder.build_rich_user_context`` walks
        to populate ``spawned_uid_to_ps_uid``. Round-tripping the UIDs here
        proves the SPAWNED_FROM traversal is symmetric with the spawn-time
        atomic writes.
        """
        await _seed_full_bundle(ps_backend, template_backends, executor)
        engage = await engagement_service.engage_pathstep(test_user, PS_UID)
        assert engage.is_ok
        spawned_at_engage = set(engage.value.spawned_instance_uids)
        assert len(spawned_at_engage) == 6

        listed = await engagement_service.list_engaged(test_user)
        assert listed.is_ok
        assert len(listed.value) == 1
        re_discovered = set(listed.value[0].spawned_instance_uids)
        assert re_discovered == spawned_at_engage, (
            "list_engaged must re-discover exactly the instances spawn just created"
        )

        # Simulating UserContextBuilder's dict comprehension (lines 421-425 of
        # user_context_builder.py) — every spawned UID maps to PS_UID.
        spawned_uid_to_ps_uid = {
            instance_uid: eng.ps_uid
            for eng in listed.value
            for instance_uid in eng.spawned_instance_uids
        }
        assert all(ps == PS_UID for ps in spawned_uid_to_ps_uid.values())
        assert set(spawned_uid_to_ps_uid.keys()) == spawned_at_engage

    async def test_activity_status_change_mid_engagement_preserves_round_trip(
        self,
        engagement_service,
        ps_backend,
        template_backends,
        instance_backends,
        executor,
        test_user,
    ):
        """Student mutates a spawned activity while the engagement is still active.

        The four-transition test ``test_complete_with_mixed_review`` mutates
        instances via ``complete_pathstep`` (which flips ``engagement_state``
        to 'owned' on keeps). This one models the other path — the student
        opens the spawned Task and marks it complete directly. The activity's
        ``status`` changes; ``engagement_state`` stays 'engaged'; the
        SPAWNED_FROM edge is untouched, so the round trip must still work.
        """
        uids = await _seed_full_bundle(ps_backend, template_backends, executor)
        engage = await engagement_service.engage_pathstep(test_user, PS_UID)
        assert engage.is_ok

        # Locate the spawned Task via SPAWNED_FROM — same traversal list_engaged uses.
        task_lookup = await executor.execute(
            query=(
                "MATCH (n:Task {user_uid: $student})-[:SPAWNED_FROM]->(:Entity {uid: $task_tpl}) "
                "RETURN n.uid AS uid"
            ),
            params={"student": test_user, "task_tpl": uids["task"]},
            operation="locate_spawned_task",
        )
        assert task_lookup.is_ok and task_lookup.value
        task_uid = task_lookup.value[0]["uid"]

        # Student-facing mutation — set status to completed via raw Cypher (no
        # dependency on TasksService here; the round-trip property is what's
        # under test, not the Tasks API).
        mutate = await executor.execute_write(
            query=("MATCH (n:Task {uid: $uid}) SET n.status = 'completed' RETURN n.uid AS uid"),
            params={"uid": task_uid},
            operation="student_completes_task",
        )
        assert mutate.is_ok

        # The round-trip query must still find this instance — the
        # SPAWNED_FROM edge is untouched and engagement_state is still 'engaged'.
        listed = await engagement_service.list_engaged(test_user)
        assert listed.is_ok
        assert task_uid in set(listed.value[0].spawned_instance_uids), (
            "Activity-side status mutation must not break the SPAWNED_FROM round trip"
        )
