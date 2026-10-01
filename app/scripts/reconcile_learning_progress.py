"""Close the learning-progress gaps the graph shows: the derived PathStep MASTERED
edge wherever every Ku a published step teaches is mastered, and the recorded
progress of every enrollment that was never recounted.

Both writers run best-effort behind an event (``KnowledgeMastered``,
``LearningPathStarted``) that is published once per transition; a detection or
write that fails after the triggering edge has committed leaves a gap, and nothing
replays the event. This one-shot reads the gaps from the graph's own state and
closes each through the same writer — publishing ``PathStepCompleted`` /
``LearningPathProgressUpdated`` / ``LearningPathCompleted`` for the transitions it
creates, so the chain runs for the reconciled state. Idempotent: a second run finds
nothing.

Usage:
    uv run scripts/reconcile_learning_progress.py --dry-run   # list the gaps, write nothing
    uv run scripts/reconcile_learning_progress.py             # close them
    ./dev reconcile-learning-progress [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # the UTC arc's bridge: before any clock read (ADR-089)


async def run(*, dry_run: bool) -> int:
    """Compose the services (CORE tier — no AI is involved), reconcile both, report."""
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
        lp_service = composed.value.lp
        if ps_service is None or lp_service is None:
            print("ERROR: PsService / LpService is not wired", file=sys.stderr)
            return 1

        verb = "would write" if dry_run else "wrote"
        exit_code = 0

        # Steps first: a step edge a reconciled enrollment's recount could count on.
        steps = await ps_service.mastery.reconcile_step_mastery(dry_run=dry_run)
        if steps.is_error:
            print(f"ERROR (step mastery): {steps.expect_error()}", file=sys.stderr)
            exit_code = 1
        else:
            print(f"{verb} {len(steps.value)} step MASTERED edge(s)")
            for step_gap in steps.value:
                print(f"  {step_gap['user_uid']} → {step_gap['ps_uid']}")

        enrollments = await lp_service.progress.reconcile_enrollment_progress(dry_run=dry_run)
        if enrollments.is_error:
            print(f"ERROR (enrollment progress): {enrollments.expect_error()}", file=sys.stderr)
            exit_code = 1
        else:
            print(f"{verb} {len(enrollments.value)} enrollment progress figure(s)")
            for enrollment_gap in enrollments.value:
                print(f"  {enrollment_gap['user_uid']} → {enrollment_gap['lp_uid']}")
        return exit_code
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="list the gaps, write nothing")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
