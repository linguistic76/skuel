#!/usr/bin/env python3
"""Print the knowledge-subgraph structural-health report, in-process (ADR-080 H1).

Composes the app's services and runs the exact gauge the admin page renders
(``AnalyticsService.analyze_knowledge_subgraph_health``) — one consolidated,
corpus-level report over the knowledge subgraph (Ku / PathStep / LearningPath /
Exercise, telemetry excluded):

  - node counts and Ku degree distribution
  - the orphan-Ku list (isolated concepts — the strongest authoring signal)
  - composition, prerequisite-DAG (with depth), ORGANIZES/MOC, and lateral coverage
  - practice coverage (PathSteps anchoring an exercise)
  - a composite GDS-readiness score + authoring-guidance flags

It is an authoring guide today and the density gauge for the deferred GDS work
(ADR-080 Horizon 2). Tier-independent — pure graph analytics, no API keys.

Usage:
    uv run scripts/knowledge_health_report.py            # human-readable summary
    uv run scripts/knowledge_health_report.py --json     # raw report as JSON
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
from typing import Any


def _print_human(report: dict[str, Any]) -> None:
    """Render the report as a readable console summary."""
    print("\n=== Knowledge-Subgraph Structural Health (ADR-080 Horizon-1) ===\n")

    print("Corpus:")
    print(f"  Kus:            {report['total_kus']}")
    print(f"  Path Steps:     {report['total_path_steps']}")
    print(f"  Learning Paths: {report['total_learning_paths']}")
    print(f"  Exercises:      {report['total_exercises']}")

    print("\nDegree distribution (all incident edges per Ku):")
    print(f"  avg degree:   {report['avg_ku_degree']:.4f}")
    print(f"  max degree:   {report['max_ku_degree']}")
    print(f"  orphan Kus:   {report['orphan_ku_count']} ({report['orphan_fraction']:.1%})")

    def _cov(name: str, metric: dict[str, Any]) -> None:
        print(
            f"  {name:<18} {metric['edge_count']:>4} edges · "
            f"{metric['participating_kus']}/{report['total_kus']} Kus "
            f"({metric['coverage']:.1%})"
        )

    print("\nStructural coverage:")
    _cov("composition:", report["composition"])
    _cov("prerequisite DAG:", report["prerequisite_dag"])
    print(f"  {'dag max depth:':<18} {report['dag_max_depth']}")
    _cov("ORGANIZES/MOC:", report["organizes"])
    print(
        f"  {'lateral:':<18} {report['lateral_edge_count']:>4} edges · "
        f"{report['lateral_density']:.3f}/Ku "
        f"({report['enablement_edge_count']} enablement edges)"
    )
    print(
        f"  {'practice:':<18} {report['path_steps_with_exercise']}/"
        f"{report['total_path_steps']} steps ({report['practice_coverage']:.1%})"
    )

    ready = "YES" if report["gds_ready"] else "not yet"
    print(f"\nGDS-readiness score: {report['gds_readiness_score']:.4f}  (ready: {ready})")

    print("\nAuthoring guidance:")
    for flag in report["flags"]:
        print(f"  • {flag}")

    if report["orphan_kus"]:
        print(f"\nOrphan Kus ({report['orphan_ku_count']}):")
        for ku in report["orphan_kus"]:
            print(f"  - {ku['uid']}  ({ku['title']})")
    print()


async def run_report(as_json: bool) -> tuple[int, dict[str, Any] | None]:
    """Compose services, measure the subgraph, and return (exit_code, report).

    Printing is the caller's job — in --json mode ``main`` runs this whole async
    lifecycle under a stdout→stderr redirect and emits the JSON afterward, so no
    bootstrap/teardown log can land on stdout.
    """
    # The report is pure graph analytics (BaseAnalyticsService, no AI in either
    # tier), so pin this process to CORE unconditionally — never merely default.
    # A `setdefault` would let an ambient `INTELLIGENCE_TIER=full` (common in a
    # FULL dev shell) drag the report through FULL compose and crash on the
    # OpenAI/Deepgram credentials it never uses. Forcing CORE honors the CLI's
    # advertised no-API-key contract; it overrides no meaningful choice, since the
    # report has no FULL-tier behavior to opt into. This process's env only —
    # child of the shell, so the user's environment is untouched.
    os.environ["INTELLIGENCE_TIER"] = "core"

    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from services_bootstrap import compose_services

    if not as_json:
        print("Connecting to Neo4j...")
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        composed = await compose_services(adapter, InMemoryEventBus())
        if composed.is_error:
            print(f"ERROR: composition failed: {composed.expect_error()}", file=sys.stderr)
            return 1, None

        analytics = composed.value.analytics
        if analytics is None:
            print("ERROR: analytics service is not wired", file=sys.stderr)
            return 1, None

        result = await analytics.analyze_knowledge_subgraph_health()
        if result.is_error:
            print(f"ERROR: {result.expect_error()}", file=sys.stderr)
            return 1, None

        return 0, dict(result.value)
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print the knowledge-subgraph structural-health report (ADR-080 H1)."
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the raw report as JSON instead of a summary"
    )
    args = parser.parse_args()

    if args.json:
        # Redirect the ENTIRE async lifecycle (compose → measure → teardown) to
        # stderr: logging's StreamHandler binds sys.stdout at configure time, which
        # happens inside this guard, so every log — including late teardown lines —
        # lands on stderr. The JSON, printed after the guard closes, is then the
        # only thing on stdout (safe to pipe to jq).
        with contextlib.redirect_stdout(sys.stderr):
            code, report = asyncio.run(run_report(as_json=True))
        if report is not None:
            print(json.dumps(report, indent=2))
        sys.exit(code)

    code, report = asyncio.run(run_report(as_json=False))
    if report is not None:
        _print_human(report)
    sys.exit(code)


if __name__ == "__main__":
    main()
