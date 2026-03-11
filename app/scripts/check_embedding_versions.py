#!/usr/bin/env python3
"""
Check Embedding Versions
========================

Analyzes embedding versions across all nodes in the database.

Reports:
- Total nodes with embeddings
- Version distribution
- Nodes needing updates (stale versions)
- Coverage by entity type

Usage:
    uv run python scripts/check_embedding_versions.py
    uv run python scripts/check_embedding_versions.py --label Ku
    uv run python scripts/check_embedding_versions.py --verbose

Created: January 2026
See: /docs/architecture/SEARCH_ARCHITECTURE.md
"""

import argparse
import asyncio
import sys
from collections import Counter, defaultdict

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
from core.services.neo4j_genai_embeddings_service import EMBEDDING_VERSION
from core.utils.logging import get_logger

logger = get_logger("skuel.scripts.embedding_versions")


async def get_nodes_with_embeddings(driver, label: str | None = None) -> list[dict]:
    """
    Get all nodes that have embeddings.

    Args:
        driver: Neo4j driver instance
        label: Optional label filter (e.g., "Ku", "Task")

    Returns:
        List of dicts with node info and embedding metadata
    """
    if label:
        query = f"""
        MATCH (n:{label})
        WHERE n.embedding IS NOT NULL
        RETURN labels(n)[0] as label,
               n.uid as uid,
               n.embedding_version as version,
               n.embedding_model as model,
               n.embedding_updated_at as updated_at,
               size(n.embedding) as dimension
        ORDER BY n.uid
        """
    else:
        query = """
        MATCH (n)
        WHERE n.embedding IS NOT NULL
        RETURN labels(n)[0] as label,
               n.uid as uid,
               n.embedding_version as version,
               n.embedding_model as model,
               n.embedding_updated_at as updated_at,
               size(n.embedding) as dimension
        ORDER BY labels(n)[0], n.uid
        """

    try:
        result = await driver.execute_query(query)
        return [dict(record) for record in result]
    except Exception as e:
        logger.error(f"Failed to query embeddings: {e}")
        return []


def analyze_versions(nodes: list[dict]) -> dict:
    """
    Analyze embedding version distribution.

    Args:
        nodes: List of node records

    Returns:
        Dict with analysis results
    """
    total = len(nodes)

    # Count by version
    version_counts = Counter(n["version"] for n in nodes)

    # Count by label
    label_counts = Counter(n["label"] for n in nodes)

    # Count by model
    model_counts = Counter(n["model"] for n in nodes)

    # Find nodes needing updates
    current_version = EMBEDDING_VERSION
    needs_update = [n for n in nodes if n["version"] != current_version]

    # Group stale nodes by label
    stale_by_label = defaultdict(list)
    for node in needs_update:
        stale_by_label[node["label"]].append(node)

    return {
        "total": total,
        "version_counts": dict(version_counts),
        "label_counts": dict(label_counts),
        "model_counts": dict(model_counts),
        "current_version": current_version,
        "needs_update": needs_update,
        "stale_by_label": dict(stale_by_label),
    }


def print_report(analysis: dict, verbose: bool = False):
    """
    Print analysis report.

    Args:
        analysis: Analysis results
        verbose: Whether to show detailed node listings
    """
    print("=" * 80)
    print("EMBEDDING VERSION ANALYSIS")
    print("=" * 80)
    print()

    print(f"Total nodes with embeddings: {analysis['total']}")
    print(f"Current version: {analysis['current_version']}")
    print()

    # Version distribution
    print("-" * 80)
    print("VERSION DISTRIBUTION")
    print("-" * 80)
    for version, count in sorted(analysis["version_counts"].items()):
        current_marker = " (CURRENT)" if version == analysis["current_version"] else ""
        percentage = (count / analysis["total"] * 100) if analysis["total"] > 0 else 0
        print(f"{version or 'None':10s} {count:5d} nodes ({percentage:5.1f}%){current_marker}")
    print()

    # Entity type distribution
    print("-" * 80)
    print("DISTRIBUTION BY ENTITY TYPE")
    print("-" * 80)
    for label, count in sorted(analysis["label_counts"].items()):
        print(f"{label:15s} {count:5d} nodes")
    print()

    # Model distribution
    print("-" * 80)
    print("DISTRIBUTION BY MODEL")
    print("-" * 80)
    for model, count in sorted(analysis["model_counts"].items()):
        model_display = model or "Unknown"
        print(f"{model_display:30s} {count:5d} nodes")
    print()

    # Nodes needing updates
    needs_update = analysis["needs_update"]
    if needs_update:
        print("-" * 80)
        print(f"NODES NEEDING UPDATES: {len(needs_update)}")
        print("-" * 80)

        for label, nodes in sorted(analysis["stale_by_label"].items()):
            print(f"\n{label}: {len(nodes)} nodes")

            if verbose:
                for node in nodes[:10]:  # Show first 10
                    version_display = node["version"] or "None"
                    print(f"  - {node['uid']:40s} (version={version_display})")

                if len(nodes) > 10:
                    print(f"  ... and {len(nodes) - 10} more")

        print()
        print(f"⚠️  Run migration script to update {len(needs_update)} stale embeddings")
        print("    uv run python scripts/migrate_embeddings_version.py")

    else:
        print("-" * 80)
        print("✅ All embeddings are up to date!")
        print("-" * 80)

    print()
    print("=" * 80)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check embedding version distribution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check all embeddings
  uv run python scripts/check_embedding_versions.py

  # Check specific entity type
  uv run python scripts/check_embedding_versions.py --label Ku

  # Verbose output (show individual nodes)
  uv run python scripts/check_embedding_versions.py --verbose
        """,
    )

    parser.add_argument("--label", help="Filter by entity label (e.g., Ku, Task, Goal)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed node listings")

    args = parser.parse_args()

    conn = Neo4jConnection()
    await conn.connect()
    driver = conn.driver

    try:
        await driver.verify_connectivity()
        logger.info("✅ Connected to Neo4j")

        # Get nodes with embeddings
        nodes = await get_nodes_with_embeddings(driver, args.label)

        if not nodes:
            print("No nodes with embeddings found.")
            if args.label:
                print(f"(filtered by label: {args.label})")
            return 0

        # Analyze
        analysis = analyze_versions(nodes)

        # Print report
        print_report(analysis, verbose=args.verbose)

        # Return exit code based on stale embeddings
        if analysis["needs_update"]:
            return 1  # Indicate updates needed
        else:
            return 0  # All up to date

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return 1

    finally:
        await conn.close()
        logger.info("✅ Disconnected from Neo4j")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
