"""Close the goal-tally gaps the graph shows: every TASK_BASED goal whose stored tally
(``current_value`` / ``target_value`` / ``progress_percentage``) disagrees with the
tasks and events that contribute to it.

The tally's trigger (``GoalContributionsChanged``) runs best-effort behind each door
that changes a contribution; a recompute that fails after the change it answers has
committed leaves the stored figure behind, and nothing replays the event. This
one-shot reads each goal's live tally and closes every gap through the same locked
recompute — publishing ``GoalProgressUpdated`` / ``GoalAchieved`` for the transitions
it writes. It is also the stored-tally step of a migration that moves contributions.
Idempotent: a second run finds nothing.

Usage:
    uv run scripts/reconcile_goal_tallies.py --dry-run   # list the gaps, write nothing
    uv run scripts/reconcile_goal_tallies.py             # close them
    ./dev reconcile-goal-tallies [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # before any clock read (ADR-089)


async def run(*, dry_run: bool) -> int:
    """Compose the services (CORE tier — no AI is involved), reconcile, report."""
    # Analog work only: pin CORE so an ambient FULL shell cannot drag the run
    # through AI composition and its credentials.
    os.environ["INTELLIGENCE_TIER"] = "core"

    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from services_bootstrap import compose_services

    print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        composed = await compose_services(adapter, InMemoryEventBus())
        if composed.is_error:
            print(f"ERROR: composition failed: {composed.expect_error()}", file=sys.stderr)
            return 1
        goals_service = composed.value.goals
        if goals_service is None:
            print("ERROR: GoalsService is not wired", file=sys.stderr)
            return 1

        gaps = await goals_service.progress.reconcile_goal_tallies(dry_run=dry_run)
        if gaps.is_error:
            print(f"ERROR: {gaps.expect_error()}", file=sys.stderr)
            return 1
        verb = "would write" if dry_run else "wrote"
        print(f"{verb} {len(gaps.value)} goal tally figure(s)")
        for gap in gaps.value:
            print(f"  {gap.user_uid} → {gap.goal_uid}: stored {gap.stored}, live {gap.live}")
        return 0
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="list the gaps, write nothing")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
