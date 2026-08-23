"""The productivity reconciliation against a real graph.

``ProductivityAnalytics.tasks_completed`` is derived — the count of the user's
tasks currently in ``completed``, refreshed by ``TaskCompleted`` /
``TaskReopened``. Three things move the true count without firing either event:
a node still holding the old lifetime tally, a task created already-completed or
deleted while completed, and the vault ``- [x]`` bulk upsert, which publishes no
task events at all. ``scripts/reconcile_productivity_analytics.py`` is the
one-shot pass that closes all three.

Everything load-bearing here is Cypher, so it is proven against the container
rather than a fake:

1. **The scan set.** The pass must reach a user whose true count is *zero* —
   that is the shape a naive ``MATCH (:Task {status: 'completed'})`` grouping
   returns no row for, and it is exactly where a stale tally hides. It must also
   reach a user with completions but no analytics node at all (the vault door),
   and leave a user with neither alone rather than littering empty nodes.
2. **Idempotence.** The second run must issue no write, not re-write the same
   numbers.
3. **``--dry-run``.** Reports without touching the graph.
4. **The completion stamps.** A reconciliation is not a completion, so
   ``first_completion_at`` / ``last_completion_at`` must come out untouched —
   they record when the user first and most recently completed something.

The DB-free contract (which users are written, that ``occurred_at`` is always
``None``) is pinned in ``tests/unit/scripts/test_reconcile_productivity_analytics.py``
so it runs on every CI job; this file is path-filtered.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio

from core.models.enums.entity_enums import EntityStatus

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import reconcile_productivity_analytics as reconciler  # type: ignore[import-not-found]

LEGACY = "user_reconcile_legacy"
ZERO = "user_reconcile_zero"
VAULT = "user_reconcile_vault"
IDLE = "user_reconcile_idle"

# Stamps seeded on every pre-existing node. A reconciliation must return them
# unchanged: they are completion moments, and this pass is not a completion.
STAMP_FIRST = "2026-01-05T09:00:00"
STAMP_LAST = "2026-06-11T17:30:00"


async def _seed_task(neo4j_driver, user_uid: str, task_uid: str, status: EntityStatus) -> None:
    """Own a Task off the user — the shape the recompute counts (ADR-086)."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (u:User {uid: $user_uid})
            MERGE (t:Entity:Task {uid: $task_uid})
            SET t.user_uid = $user_uid,
                t.entity_type = 'task',
                t.title = $task_uid,
                t.status = $status
            MERGE (u)-[:OWNS]->(t)
            """,
            user_uid=user_uid,
            task_uid=task_uid,
            status=status.value,
        )
        await result.consume()


async def _seed_analytics(neo4j_driver, user_uid: str, tasks_completed: int) -> None:
    """A pre-existing node holding a legacy tally and real completion stamps."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MERGE (a:ProductivityAnalytics {user_uid: $user_uid})
            SET a.tasks_completed = $tasks_completed,
                a.first_completion_at = datetime($first),
                a.last_completion_at = datetime($last)
            """,
            user_uid=user_uid,
            tasks_completed=tasks_completed,
            first=STAMP_FIRST,
            last=STAMP_LAST,
        )
        await result.consume()


async def _analytics(neo4j_driver, user_uid: str):
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (a:ProductivityAnalytics {user_uid: $user_uid})
            RETURN a.tasks_completed AS count,
                   a.first_completion_at AS first,
                   a.last_completion_at AS last
            """,
            user_uid=user_uid,
        )
        return await result.single()


@pytest.mark.asyncio
@pytest.mark.integration
class TestProductivityAnalyticsReconciliation:
    """The one-shot pass, exercised against the Neo4j testcontainer."""

    @pytest_asyncio.fixture
    async def backend(self, neo4j_driver, clean_neo4j):
        from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
        from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

        return CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))

    @pytest_asyncio.fixture
    async def seeded(self, neo4j_driver, backend):
        """One user per way the stored count and the graph can disagree."""
        # Legacy tally: the node says 9, the graph says 2 (the third is open).
        await _seed_analytics(neo4j_driver, LEGACY, 9)
        await _seed_task(neo4j_driver, LEGACY, "task.legacy_a", EntityStatus.COMPLETED)
        await _seed_task(neo4j_driver, LEGACY, "task.legacy_b", EntityStatus.COMPLETED)
        await _seed_task(neo4j_driver, LEGACY, "task.legacy_open", EntityStatus.ACTIVE)

        # Every completed task since deleted: the node says 9, the graph says 0.
        await _seed_analytics(neo4j_driver, ZERO, 9)

        # The vault `- [x]` door: completions arrived, no event, so no node.
        await _seed_task(neo4j_driver, VAULT, "task.vault_a", EntityStatus.COMPLETED)
        await _seed_task(neo4j_driver, VAULT, "task.vault_b", EntityStatus.COMPLETED)
        await _seed_task(neo4j_driver, VAULT, "task.vault_c", EntityStatus.COMPLETED)

        # IDLE owns nothing and has no node — the control for the scan set.
        return backend

    # ====================================================================
    # THE SCAN SET
    # ====================================================================

    async def test_a_legacy_tally_is_corrected_to_the_true_count(self, neo4j_driver, seeded):
        """The headline case: a lifetime event tally served under the new meaning."""
        assert await reconciler.reconcile(seeded, dry_run=False) == 0

        record = await _analytics(neo4j_driver, LEGACY)
        assert record["count"] == 2, "the open task must not be counted"

    async def test_zero_completed_tasks_reconciles_to_zero(self, neo4j_driver, seeded):
        """Not skipped — this is where a stale tally hides forever.

        The user owns no completed task at all, so a grouping query keyed on
        ``(:Task {status: 'completed'})`` returns no row for them. The scan set's
        "has a ProductivityAnalytics node" arm is what reaches them.
        """
        assert await reconciler.reconcile(seeded, dry_run=False) == 0

        record = await _analytics(neo4j_driver, ZERO)
        assert record["count"] == 0

    async def test_completions_with_no_node_get_one(self, neo4j_driver, seeded):
        """The vault ``- [x]`` door: no event ever fired, so no node exists."""
        assert await _analytics(neo4j_driver, VAULT) is None

        assert await reconciler.reconcile(seeded, dry_run=False) == 0

        record = await _analytics(neo4j_driver, VAULT)
        assert record is not None
        assert record["count"] == 3
        # Nothing is known about *when* those completions happened, and the pass
        # refuses to invent it. The velocity these tasks contribute comes from
        # their own `completion_date` stamps, not from these node-level ones, so
        # leaving them null costs the report nothing it could honestly have.
        assert record["first"] is None
        assert record["last"] is None

    async def test_a_user_with_nothing_recorded_is_left_alone(self, neo4j_driver, seeded):
        """No tasks, no node — nothing to record, so no node is littered.

        ``get_productivity_metrics`` already reads 0 for an absent node, and the
        graph is node-capped.
        """
        assert await reconciler.reconcile(seeded, dry_run=False) == 0

        assert await _analytics(neo4j_driver, IDLE) is None

    async def test_another_users_completions_do_not_leak(self, neo4j_driver, seeded):
        """The count is scoped by the ``:OWNS`` edge, not by label."""
        assert await reconciler.reconcile(seeded, dry_run=False) == 0

        assert (await _analytics(neo4j_driver, LEGACY))["count"] == 2
        assert (await _analytics(neo4j_driver, VAULT))["count"] == 3

    # ====================================================================
    # IDEMPOTENCE, DRY RUN, AND THE STAMPS
    # ====================================================================

    async def test_the_second_run_is_a_no_op(self, neo4j_driver, seeded):
        """Idempotent at the write level, not merely at the value level.

        After the first pass nothing drifts, so the second issues no write at
        all — the property that lets this be re-run without thought.
        """
        assert await reconciler.reconcile(seeded, dry_run=False) == 0

        surveyed = await reconciler.find_drift(seeded)
        assert surveyed.is_ok
        _, drifted = surveyed.value
        assert drifted == [], f"still drifting after one pass: {drifted}"

        before = await _analytics(neo4j_driver, LEGACY)
        assert await reconciler.reconcile(seeded, dry_run=False) == 0
        after = await _analytics(neo4j_driver, LEGACY)
        assert after["count"] == before["count"] == 2
        assert after["first"] == before["first"]
        assert after["last"] == before["last"]

    async def test_dry_run_writes_nothing(self, neo4j_driver, seeded):
        """Look before leaping: the drift is reported and the graph is untouched."""
        assert await reconciler.reconcile(seeded, dry_run=True) == 0

        assert (await _analytics(neo4j_driver, LEGACY))["count"] == 9
        assert (await _analytics(neo4j_driver, ZERO))["count"] == 9
        assert await _analytics(neo4j_driver, VAULT) is None

        # And it did not consume the drift it reported.
        surveyed = await reconciler.find_drift(seeded)
        assert {d["user_uid"] for d in surveyed.value[1]} == {LEGACY, ZERO, VAULT}

    async def test_the_completion_stamps_survive_a_reconcile(self, neo4j_driver, seeded):
        """A reconciliation is not a completion moment.

        ``last_completion_at`` records when the user most recently completed
        something; moving it here would make every maintenance run look like a
        burst of work while looking like bookkeeping.
        """
        before = await _analytics(neo4j_driver, LEGACY)

        assert await reconciler.reconcile(seeded, dry_run=False) == 0

        after = await _analytics(neo4j_driver, LEGACY)
        assert after["count"] != before["count"], "positive control: something was written"
        assert after["first"] == before["first"]
        assert after["last"] == before["last"]

    async def test_the_survey_reports_the_stored_value_and_the_true_count(self, seeded):
        """What ``--dry-run`` renders, read straight off the backend."""
        surveyed = await reconciler.find_drift(seeded)
        assert surveyed.is_ok
        in_scope, drifted = surveyed.value

        assert in_scope == 3, "IDLE has neither a node nor a task — out of scope"
        by_user = {d["user_uid"]: (d["stored"], d["actual"]) for d in drifted}
        assert by_user == {LEGACY: (9, 2), ZERO: (9, 0), VAULT: (None, 3)}
