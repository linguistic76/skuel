#!/usr/bin/env python3
"""Prune unbounded-growth telemetry, in-process (ADR-080 Horizon 0).

A ONE-SHOT maintenance run — no background loop, so the CORE "no background
workers" guarantee holds. It age-prunes the telemetry types that dwarf the
curriculum and would otherwise breach the AuraDB Free node cap:

  - :AuthEvent            (security audit trail)      — TelemetryRetention.AUTH_EVENT_DAYS
  - :SearchEvent          (discovery-analytics log)   — TelemetryRetention.SEARCH_EVENT_DAYS
  - :Interaction          (learning-loop events)      — TelemetryRetention.INTERACTION_DAYS
  - :VIEWED edges         (stale learner view-state)  — TelemetryRetention.VIEWED_DAYS
  - expired :Session / :PasswordResetToken (own expires_at — not age-based)

Saved discussions (:ConversationSession) are deliberately OUT OF SCOPE — they are
explicitly-kept user content (ADR-078 "Save this chat"), not auto-accreting
telemetry, so a retention run never touches them.

Windows live in ``core/constants.py`` (``TelemetryRetention``). ``--days N``
overrides every age-based window uniformly; it does NOT change the expired
Session/token rule (those prune on their own stored ``expires_at``). ``--dry-run``
reports per-type counts and deletes nothing.

Tier-independent — pure graph maintenance, no API keys. The initial connect
tolerates a paused/waking AuraDB Free instance (bounded backoff, ADR-080 H0).

Usage:
    uv run scripts/telemetry_retention.py --dry-run          # report, delete nothing
    uv run scripts/telemetry_retention.py                    # prune with default windows
    uv run scripts/telemetry_retention.py --days 30          # prune everything older than 30d
    uv run scripts/telemetry_retention.py --days 30 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys


async def run_retention(*, days_override: int | None, batch_size: int, dry_run: bool) -> int:
    """Connect, prune (or count) each telemetry type, print a report, return exit code."""
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from adapters.persistence.neo4j.session_backend import SessionBackend
    from adapters.persistence.neo4j.telemetry_retention_backend import TelemetryRetentionBackend
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.constants import TelemetryRetention

    def _window(default_days: int) -> int:
        return days_override if days_override is not None else default_days

    print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        driver = adapter.get_driver()
        backend = TelemetryRetentionBackend(Neo4jQueryExecutor(driver))
        session_backend = SessionBackend(driver)

        # (label, coroutine, window_days | None). None window = expiry-based.
        age_targets = [
            (
                "AuthEvent",
                backend.prune_auth_events,
                _window(TelemetryRetention.AUTH_EVENT_DAYS),
            ),
            (
                "SearchEvent",
                backend.prune_search_events,
                _window(TelemetryRetention.SEARCH_EVENT_DAYS),
            ),
            (
                "Interaction",
                backend.prune_interactions,
                _window(TelemetryRetention.INTERACTION_DAYS),
            ),
            (
                "VIEWED edges",
                backend.prune_viewed_edges,
                _window(TelemetryRetention.VIEWED_DAYS),
            ),
        ]

        report: list[tuple[str, int]] = []
        for label, prune, window_days in age_targets:
            result = await prune(days=window_days, batch_size=batch_size, dry_run=dry_run)
            if result.is_error:
                print(f"ERROR pruning {label}: {result.expect_error()}", file=sys.stderr)
                return 1
            report.append((f"{label} (>{window_days}d)", result.value))

        # Expired sessions / reset tokens: prune on their own expires_at (reuse
        # the existing SessionBackend maintenance — not age-based, so --days does
        # not apply). Dry-run counts without deleting.
        if dry_run:
            sessions = await session_backend.count_expired_sessions()
            tokens = await session_backend.count_expired_tokens()
        else:
            sessions = await session_backend.cleanup_expired_sessions()
            tokens = await session_backend.cleanup_expired_tokens()
        for label, res in (("Expired sessions", sessions), ("Expired reset tokens", tokens)):
            if res.is_error:
                print(f"ERROR pruning {label}: {res.expect_error()}", file=sys.stderr)
                return 1
            report.append((label, res.value))

        _print_report(report, dry_run=dry_run)
        return 0
    finally:
        await adapter.close()


def _print_report(report: list[tuple[str, int]], *, dry_run: bool) -> None:
    """Render per-type counts and a total to stdout."""
    verb = "would prune" if dry_run else "pruned"
    header = "Telemetry Retention — DRY RUN (nothing deleted)" if dry_run else "Telemetry Retention"
    print(f"\n=== {header} ===\n")
    width = max(len(label) for label, _ in report)
    for label, count in report:
        print(f"  {label:<{width}}  {count:>8,} {verb}")
    total = sum(count for _, count in report)
    print(f"  {'-' * (width + 18)}")
    print(f"  {'TOTAL':<{width}}  {total:>8,} {verb}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prune unbounded-growth telemetry (ADR-080 Horizon 0). One-shot."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="override every age-based window to N days (default: per-type windows "
        "in core/constants.py TelemetryRetention). Does not affect expired "
        "session/token cleanup (they use their own expires_at).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report per-type counts without deleting anything",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="rows deleted per transaction (default: "
        "core/constants.py TelemetryRetention.BATCH_SIZE)",
    )
    args = parser.parse_args()

    if args.days is not None and args.days < 0:
        parser.error("--days must be >= 0")
    if args.batch_size is not None and args.batch_size < 1:
        parser.error("--batch-size must be >= 1")

    from core.constants import TelemetryRetention

    batch_size = args.batch_size if args.batch_size is not None else TelemetryRetention.BATCH_SIZE
    sys.exit(
        asyncio.run(
            run_retention(days_override=args.days, batch_size=batch_size, dry_run=args.dry_run)
        )
    )


if __name__ == "__main__":
    main()
