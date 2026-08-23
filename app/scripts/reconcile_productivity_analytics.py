#!/usr/bin/env python3
"""Recompute every user's ``ProductivityAnalytics.tasks_completed`` from the graph.

A ONE-SHOT maintenance run — no background loop, no scheduler, so the CORE-tier
"no background workers" guarantee holds (same shape as
``./dev telemetry-retention`` and ``./dev embed-backfill``). Tier-independent:
pure graph maintenance, no API keys.

``tasks_completed`` stopped being a tally and became a **derived** value — the
count of the user's tasks currently in ``completed``, recomputed on
``TaskCompleted`` and ``TaskReopened``. A derived value is only as good as the
events that refresh it, and three things move the true count without firing
either:

1. **Legacy values.** Nodes written under the old ``counter = counter + 1``
   still hold a lifetime *event* tally, and ``get_productivity_metrics`` serves
   that stored number directly — under the new meaning — until some unrelated
   completion happens to fire.
2. **Create and delete.** A task can be created already ``completed``, and a
   completed task can be deleted. Both change the true count, and neither
   ``TaskCreated`` nor ``TaskDeleted`` carries a status, so no subscriber could
   even tell whether it needed to care: wiring them would mean a full per-user
   count on *every* task create and delete.
3. **The vault ``- [x]`` door.** The bulk upsert publishes no task events at
   all, so no amount of event wiring reaches the highest-volume create path.

One idempotent pass covers all three, and costs the create/delete hot paths
nothing. It is deliberately not three separate fixes: the event-wiring one
would have missed (3) entirely while taxing (2).

**Idempotent, and demonstrably so.** The pass surveys first and writes only for
users whose stored value disagrees with the graph, so a second run issues *zero*
writes. The survey never decides a value — the number written is counted inside
the write statement itself (``recompute_productivity_analytics``, reused
unchanged), so a user who drifts between the survey and the write is skipped
rather than given a stale count, and the next run picks them up.

**It does not invent completion moments.** ``first_completion_at`` and
``last_completion_at`` are completion stamps and a reconciliation is not a
completion, so the write passes ``occurred_at=None`` and leaves both exactly
where they are. ``last_completion_at`` records when the user most recently
completed something; moving it here would make a maintenance run look like a
burst of work.

Usage:
    uv run scripts/reconcile_productivity_analytics.py --dry-run   # report, write nothing
    uv run scripts/reconcile_productivity_analytics.py             # reconcile
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import TYPE_CHECKING

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
    from core.ports.query_types import ProductivityDriftRow


async def find_drift(backend: CrossDomainBackend) -> Result[tuple[int, list[ProductivityDriftRow]]]:
    """Survey the graph read-only: ``(users_in_scope, drifted)``.

    The backend hands back typed rows that already keep ``stored=None`` (no
    node at all) distinct from ``stored=0`` (a node saying zero), so the filter
    is a plain disagreement test: a missing node drifts whenever the user has
    completed tasks, and ``stored == actual`` is left alone — which is what
    makes the second run a no-op.
    """
    survey = await backend.survey_productivity_analytics_drift()
    if survey.is_error:
        return Result.fail(survey)

    rows = survey.value or []
    drifted = [row for row in rows if row["stored"] != row["actual"]]
    return Result.ok((len(rows), drifted))


async def reconcile(backend: CrossDomainBackend, *, dry_run: bool) -> int:
    """Survey, report, and (unless ``--dry-run``) correct. Returns an exit code."""
    surveyed = await find_drift(backend)
    if surveyed.is_error:
        print(f"ERROR surveying productivity analytics: {surveyed.expect_error()}", file=sys.stderr)
        return 1
    in_scope, drifted = surveyed.value

    if dry_run or not drifted:
        _print_report(in_scope=in_scope, drifted=drifted, failed=[], dry_run=dry_run)
        return 0

    failed: list[tuple[str, str]] = []
    for drift in drifted:
        # occurred_at=None: a reconciliation is not a completion moment. The
        # count is recomputed inside this statement, so the value written is
        # never the one the survey read.
        result = await backend.recompute_productivity_analytics(
            user_uid=drift["user_uid"], occurred_at=None
        )
        if result.is_error:
            failed.append((drift["user_uid"], str(result.expect_error())))

    _print_report(in_scope=in_scope, drifted=drifted, failed=failed, dry_run=False)

    # Prove the pass converged rather than asserting it. A user still drifting
    # here either failed above or was written by another door mid-run; both are
    # fixed by re-running, and neither should read as success.
    verified = await find_drift(backend)
    if verified.is_error:
        print(f"ERROR verifying productivity analytics: {verified.expect_error()}", file=sys.stderr)
        return 1
    _, remaining = verified.value
    if remaining:
        print(
            f"\nFAILED: {len(remaining)} user(s) still drift after the write "
            f"({', '.join(d['user_uid'] for d in remaining[:10])}). Re-run to converge.",
            file=sys.stderr,
        )
        return 1
    print("Verified: every in-scope user's tasks_completed now matches the graph.\n")
    return 0 if not failed else 1


def _print_report(
    *,
    in_scope: int,
    drifted: list[ProductivityDriftRow],
    failed: list[tuple[str, str]],
    dry_run: bool,
) -> None:
    """Render the scan set, the drift, and each corrected user."""
    verb = "would correct" if dry_run else "corrected"
    header = (
        "ProductivityAnalytics Reconciliation — DRY RUN (nothing written)"
        if dry_run
        else "ProductivityAnalytics Reconciliation"
    )
    print(f"\n=== {header} ===\n")
    print(f"  Users in scope   {in_scope:>8,}")
    print(f"  Already correct  {in_scope - len(drifted):>8,}")
    print(f"  Drifted          {len(drifted):>8,} {verb}")

    if not drifted:
        print("\n  Nothing to reconcile — every stored count already matches the graph.\n")
        return

    print(f"\n  {'user':<28} {'stored':>8}     {'actual':>8}")
    for drift in drifted:
        # "unset" is not "0": no node at all is a different state from a node
        # recording zero completions, and the operator has to be able to see it.
        stored = "unset" if drift["stored"] is None else f"{drift['stored']:,}"
        print(f"  {drift['user_uid']:<28} {stored:>8}  →  {drift['actual']:>8,}")

    if failed:
        print(f"\n  FAILED ({len(failed)}):")
        for user_uid, reason in failed[:20]:
            print(f"    {user_uid}: {reason}")
        if len(failed) > 20:
            print(f"    ... and {len(failed) - 20} more")
    print()


async def run_reconciliation(*, dry_run: bool) -> int:
    """Connect to Neo4j and run one reconciliation pass."""
    from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from adapters.persistence.neo4j_adapter import Neo4jAdapter

    print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        backend = CrossDomainBackend(Neo4jQueryExecutor(adapter.get_driver()))
        return await reconcile(backend, dry_run=dry_run)
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Recompute ProductivityAnalytics.tasks_completed for every user from "
            "the graph. One-shot, idempotent, safe to re-run."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report every drifted user without writing anything",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run_reconciliation(dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
