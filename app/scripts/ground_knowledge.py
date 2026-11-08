#!/usr/bin/env python3
"""Ground UserEntries or Tasks to Kus, in-process.

``--source entries`` (the default) grounds the entries on a grounded pipeline
(``Pipeline.knowledge_grounded``: knowledge notes and activity notes, periodic
notes included) with a stored embedding; a ``private: true`` entry is never
grounded. ``--source tasks`` grounds embedded tasks; a cancelled task is never
grounded.

Composes the app's services and runs the exact grounding pass the triggers run
(an entry's post-sync pass, a task's stored embedding) — as a backfill over every
pending entity (or one user's), with a dry-run default so the threshold's output
can be eyeballed before any edge is written.

What a pass does (KnowledgeGroundingService):
  1. Candidates: each pending entity's STORED embedding queries the Ku vector
     index at the configured threshold (default 0.72). CORE-tier safe — reads
     vectors, embeds nothing.
  2. Judge (FULL tier): an LLM filters candidates for genuine engagement; on
     CORE candidates pass through unjudged. Dry runs exercise the judge too,
     so the printout is exactly what --apply would write.
  3. Apply: eager ``APPLIES_KNOWLEDGE {inferred, confidence, grounded_at}``
     edges + one substance event per NEW edge (``KnowledgeReflectedInEntry`` for
     an entry, ``KnowledgeAppliedInTask`` for a task; handlers run in-process on
     the composed bus), then the per-entity grounded stamp.

Already-linked Kus and user-removed (rejected) links are never re-written or
re-counted; ``--force`` re-runs entities whose stamp is current (still
idempotent — existing edges are skipped, only genuinely new ones publish).

Usage:
    uv run scripts/ground_knowledge.py                        # dry run, entries, all users
    uv run scripts/ground_knowledge.py --source tasks         # dry run, tasks, all users
    uv run scripts/ground_knowledge.py --user user_mike       # dry run, one user
    uv run scripts/ground_knowledge.py --apply                # write edges + events
    uv run scripts/ground_knowledge.py --threshold 0.75       # calibration experiment

``--threshold`` is read through ``GroundingConfig``, which refuses a value below the
knowledge-link floor (``KnowledgeLinkConfidence.FLOOR``) before the script connects.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # the UTC arc's bridge: before any clock read (ADR-089)


async def run_grounding(
    source: str,
    user_uid: str | None,
    apply: bool,
    force: bool,
    threshold: float | None,
) -> int:
    from dataclasses import replace

    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.models.type_hints import UserUID
    from services_bootstrap import compose_services

    print("Connecting to Neo4j...")
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        composed = await compose_services(adapter, InMemoryEventBus())
        if composed.is_error:
            print(f"ERROR: composition failed: {composed.expect_error()}", file=sys.stderr)
            return 1

        services = composed.value
        grounding = services.task_grounding if source == "tasks" else services.entry_grounding
        if grounding is None:
            print(f"ERROR: {source} grounding is not wired", file=sys.stderr)
            return 1
        if threshold is not None:
            grounding.config = replace(grounding.config, threshold=threshold)

        mode = "APPLY" if apply else "DRY RUN"
        scope = user_uid or "all users"
        print(
            f"Grounding pass [{mode}] — {source}, scope: {scope}, threshold: "
            f"{grounding.config.threshold}, force: {force}, "
            f"judge: {'on' if grounding.judge_available else 'off (CORE / no chat port)'}\n"
        )

        result = await grounding.ground_pending(
            UserUID(user_uid) if user_uid else None, force=force, apply=apply
        )
        if result.is_error:
            print(f"ERROR: grounding failed: {result.expect_error()}", file=sys.stderr)
            return 1

        report = result.value
        verb = "wrote" if apply else "would write"
        for outcome in report.outcomes:
            if outcome.error is not None:
                print(f"✗ {outcome.source_uid}  {outcome.source_title!r}")
                print(f"    ERROR: {outcome.error}")
                continue
            if not outcome.written and not outcome.rejected_by_judge:
                continue
            print(f"• {outcome.source_uid}  {outcome.source_title!r}")
            for candidate in outcome.written:
                print(f"    {verb}  {candidate.similarity:.4f}  {candidate.ku_uid}")
            for candidate in outcome.rejected_by_judge:
                why = f" — {candidate.rationale}" if candidate.rationale else ""
                print(f"    judge-rejected  {candidate.similarity:.4f}  {candidate.ku_uid}{why}")
            if outcome.skipped_existing or outcome.skipped_rejected:
                print(
                    f"    (skipped: {outcome.skipped_existing} already linked, "
                    f"{outcome.skipped_rejected} user-rejected)"
                )

        print(
            f"\n=== {mode} summary ===\n"
            f"  {source} scanned:   {report.scanned}\n"
            f"  {source} w/ writes: {report.with_writes}\n"
            f"  edges {verb}: {report.edges_written}\n"
            f"  {source} failed:    {report.failed}"
        )
        if not apply:
            print("\nDRY RUN — nothing written. Re-run with --apply to execute.")
        return 0
    finally:
        await adapter.close()


def _threshold(text: str) -> float:
    """A similarity threshold ``GroundingConfig`` accepts; argparse reports its refusal."""
    from core.services.knowledge_grounding_service import GroundingConfig

    value = float(text)
    try:
        GroundingConfig(threshold=value)
    except ValueError as refusal:
        raise argparse.ArgumentTypeError(str(refusal)) from refusal
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ground UserEntries or Tasks to Kus (dry-run default)."
    )
    parser.add_argument(
        "--source",
        choices=("entries", "tasks"),
        default="entries",
        help="what to ground: entries on a grounded pipeline (default) or tasks",
    )
    parser.add_argument("--user", help="scope the pass to one user_uid (default: all users)")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write edges + substance events (default is dry-run: print the plan, change nothing)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-run entities whose grounding stamp is current (existing edges still skipped)",
    )
    parser.add_argument(
        "--threshold",
        type=_threshold,
        help=(
            "override the similarity threshold for this run (calibration experiments); "
            "not below the knowledge-link floor"
        ),
    )
    args = parser.parse_args()
    sys.exit(
        asyncio.run(run_grounding(args.source, args.user, args.apply, args.force, args.threshold))
    )


if __name__ == "__main__":
    main()
