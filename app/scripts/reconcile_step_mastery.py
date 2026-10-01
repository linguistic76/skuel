"""Close step-mastery gaps: write (User)-[:MASTERED]->(PathStep) wherever every Ku the
step teaches is mastered and the step's own edge is absent.

The derived writer (``PsMasteryService.handle_knowledge_mastered``) runs best-effort
behind ``KnowledgeMastered``; a detection or write that fails after the Ku edge has
committed leaves a gap, and the transition event is not replayed. This one-shot
reads the gaps from the graph's own state and closes each through the same writer,
which publishes ``PathStepCompleted`` for the edge it creates — so the path-progress
chain runs for the reconciled step. Idempotent: a second run finds nothing.

Usage:
    uv run scripts/reconcile_step_mastery.py --dry-run   # list the gaps, write nothing
    uv run scripts/reconcile_step_mastery.py             # close them
    ./dev reconcile-step-mastery [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # the UTC arc's bridge: before any clock read (ADR-089)


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
        ps_service = composed.value.ps
        if ps_service is None:
            print("ERROR: PsService is not wired", file=sys.stderr)
            return 1

        result = await ps_service.mastery.reconcile_step_mastery(dry_run=dry_run)
        if result.is_error:
            print(f"ERROR: {result.expect_error()}", file=sys.stderr)
            return 1

        gaps = result.value
        verb = "would write" if dry_run else "wrote"
        print(f"{verb} {len(gaps)} step MASTERED edge(s)")
        for gap in gaps:
            print(f"  {gap['user_uid']} → {gap['ps_uid']}")
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
