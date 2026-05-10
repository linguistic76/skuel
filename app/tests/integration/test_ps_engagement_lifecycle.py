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
    /home/mike/.claude/plans/skip-when-do-idempotent-shell.md  § Phase 4 verification
    project_pathstep_lifecycle_contract.md (memory)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.choice.choice import Choice
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

STUDENT_UID = "user.test_ps_engagement"
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
        executor=executor,
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
            "MERGE (u:User {uid: $uid}) "
            "ON CREATE SET u.title = $uid, u.created_at = datetime($ts)",
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
        query=(
            "MATCH (ps {uid: $ps}), (t {uid: $t}) "
            f"MERGE (ps)-[r:{edge}]->(t) "
            "RETURN r"
        ),
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
            due_offset=RelativeOffset(days=7),
            fulfills_goal_template_uid=uids["goal"],
            reinforces_habit_template_uid=uids["habit"],
        )
        goal = GoalTemplate(
            uid=uids["goal"],
            title="Master the topic",
            target_offset=RelativeOffset(days=30),
            inspired_by_choice_template_uid=uids["choice"],
        )
    else:
        task = TaskTemplate(
            uid=uids["task"],
            title="Practice problem",
            due_offset=RelativeOffset(days=7),
        )
        goal = GoalTemplate(
            uid=uids["goal"],
            title="Master the topic",
            target_offset=RelativeOffset(days=30),
        )

    habit = HabitTemplate(uid=uids["habit"], title="Daily review")
    event = EventTemplate(
        uid=uids["event"], title="Cohort kickoff", event_offset=RelativeOffset(days=1)
    )
    choice = ChoiceTemplate(uid=uids["choice"], title="Track selection")
    principle = PrincipleTemplate(uid=uids["principle"], title="Practice over theory")

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
            "MATCH (n {user_uid: $student, template_uid: t.uid}) "
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

        # Every instance carries template_uid + engagement_state="engaged".
        states_res = await executor.execute(
            query=(
                "MATCH (ps {uid: $ps})-[:HAS_TASK_TEMPLATE|HAS_GOAL_TEMPLATE"
                "|HAS_HABIT_TEMPLATE|HAS_EVENT_TEMPLATE|HAS_CHOICE_TEMPLATE"
                "|HAS_PRINCIPLE_TEMPLATE]->(t) "
                "MATCH (n {user_uid: $student, template_uid: t.uid}) "
                "RETURN n.engagement_state AS state, n.template_uid AS tpl"
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
        uids = await _seed_full_bundle(
            ps_backend, template_backends, executor, cross_refs=True
        )

        result = await engagement_service.engage_pathstep(test_user, PS_UID)
        assert result.is_ok

        # Find the spawned task instance, check its fulfills_goal_uid points
        # at the spawned goal instance (NOT the template UID).
        ref_res = await executor.execute(
            query=(
                "MATCH (task {user_uid: $student, template_uid: $task_tpl}) "
                "MATCH (goal {user_uid: $student, template_uid: $goal_tpl}) "
                "RETURN task.fulfills_goal_uid AS goal_ref, "
                "       task.reinforces_habit_uid AS habit_ref, "
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
        assert record["habit_ref"] is not None

    async def test_engage_fails_for_empty_pathstep(
        self, engagement_service, ps_backend, test_user
    ):
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
                "MATCH (n {user_uid: $student, template_uid: t.uid}) "
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
                "MATCH (n {user_uid: $student, template_uid: t.uid}) "
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
