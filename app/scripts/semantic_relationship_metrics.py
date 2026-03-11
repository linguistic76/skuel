"""
Semantic Relationship Metrics - Track Activation Progress
==========================================================

Track progress on semantic relationship activation initiative.
Shows which relationships are active, usage counts, and activation percentage.

Usage:
    uv run python scripts/semantic_relationship_metrics.py
    uv run python scripts/semantic_relationship_metrics.py --detailed
    uv run python scripts/semantic_relationship_metrics.py --export metrics.json
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

# Tier definitions (from activation plan)
TIER_1_RELATIONSHIPS = [
    "habit:triggers_after",
    "learn:deepens_understanding",
    "learn:extends_pattern",
    "habit:builds_capacity_for",
    "learn:reinforces_knowledge",
]

TIER_2_RELATIONSHIPS = [
    "cross:discovered_through",
    "learn:simplifies",
    "learn:elaborates_on",
    "cross:informed_by_knowledge",
    "cross:shares_principle_with",
    "skill:practices_technique",
]

TIER_3_RELATIONSHIPS = [
    "learn:analogous_to",
    "learn:contrasts_with",
    "learn:alternative_approach_to",
    "cross:reveals_pattern_in",
    "concept:derives_from",
    "concept:generalizes",
]


async def get_semantic_relationship_metrics() -> dict:
    """
    Get comprehensive metrics on semantic relationship usage.

    Returns:
        dict: Metrics including activation counts, usage stats, etc.
    """
    conn = Neo4jConnection()
    await conn.connect()
    driver = conn.driver

    try:
        async with driver.session() as session:
            # Query all relationship types with usage counts
            query = """
            CALL db.relationshipTypes() YIELD relationshipType
            WHERE relationshipType CONTAINS ':'  // Semantic types have namespace

            OPTIONAL MATCH ()-[r]->()
            WHERE type(r) = relationshipType

            RETURN relationshipType, count(r) as usage_count
            ORDER BY usage_count DESC
            """

            result = await session.run(query)
            records = await result.data()

            # Build metrics
            metrics = {
                "timestamp": datetime.now().isoformat(),
                "total_semantic_types_defined": 80,  # From semantic_relationships.py
                "tier_1": {
                    "target": len(TIER_1_RELATIONSHIPS),
                    "active": 0,
                    "relationships": {},
                },
                "tier_2": {
                    "target": len(TIER_2_RELATIONSHIPS),
                    "active": 0,
                    "relationships": {},
                },
                "tier_3": {
                    "target": len(TIER_3_RELATIONSHIPS),
                    "active": 0,
                    "relationships": {},
                },
                "total_active": 0,
                "activation_percentage": 0.0,
                "namespaces": {},
                "top_10_used": [],
                "unused_count": 0,
                "unused_types": [],
            }

            # Process each relationship type
            for record in records:
                rel_type = record["relationshipType"]
                count = record["usage_count"]

                # Categorize by tier
                tier = None
                if rel_type in TIER_1_RELATIONSHIPS:
                    tier = "tier_1"
                elif rel_type in TIER_2_RELATIONSHIPS:
                    tier = "tier_2"
                elif rel_type in TIER_3_RELATIONSHIPS:
                    tier = "tier_3"

                # Track if active
                is_active = count > 0

                if tier:
                    metrics[tier]["relationships"][rel_type] = {
                        "count": count,
                        "active": is_active,
                    }
                    if is_active:
                        metrics[tier]["active"] += 1

                # Track namespace usage
                namespace = rel_type.split(":")[0]
                if namespace not in metrics["namespaces"]:
                    metrics["namespaces"][namespace] = {
                        "total": 0,
                        "active": 0,
                        "usage_count": 0,
                    }

                metrics["namespaces"][namespace]["total"] += 1
                if is_active:
                    metrics["namespaces"][namespace]["active"] += 1
                    metrics["namespaces"][namespace]["usage_count"] += count
                    metrics["total_active"] += 1

                # Top 10 used
                if len(metrics["top_10_used"]) < 10 and is_active:
                    metrics["top_10_used"].append({"type": rel_type, "count": count})

                # Unused tracking
                if not is_active:
                    metrics["unused_count"] += 1
                    metrics["unused_types"].append(rel_type)

            # Calculate activation percentage
            metrics["activation_percentage"] = (
                metrics["total_active"] / metrics["total_semantic_types_defined"]
            ) * 100

            return metrics

    finally:
        await conn.close()


def print_metrics_summary(metrics: dict):
    """Print a human-readable summary of metrics."""

    print("\n" + "=" * 80)
    print("SEMANTIC RELATIONSHIP ACTIVATION METRICS")
    print("=" * 80)
    print(f"Generated: {metrics['timestamp']}")
    print()

    # Overall stats
    print("📊 OVERALL STATISTICS")
    print("-" * 80)
    print(f"  Total Semantic Types Defined: {metrics['total_semantic_types_defined']}")
    print(f"  Total Active: {metrics['total_active']}")
    print(f"  Unused: {metrics['unused_count']}")
    print(f"  Activation Percentage: {metrics['activation_percentage']:.1f}%")
    print()

    # Tier progress
    print("🎯 TIER PROGRESS")
    print("-" * 80)

    for tier_name, tier_label in [
        ("tier_1", "Tier 1 (High Impact, Easy Win)"),
        ("tier_2", "Tier 2 (Medium Impact)"),
        ("tier_3", "Tier 3 (Advanced)"),
    ]:
        tier = metrics[tier_name]
        active = tier["active"]
        target = tier["target"]
        percentage = (active / target * 100) if target > 0 else 0

        status_bar = "█" * int(percentage / 10) + "░" * (10 - int(percentage / 10))

        print(f"  {tier_label}")
        print(f"    Progress: {active}/{target} ({percentage:.0f}%) {status_bar}")

        # Show individual relationship status
        for rel_type, data in tier["relationships"].items():
            status = "✅" if data["active"] else "❌"
            count_str = f"({data['count']} uses)" if data["active"] else "(unused)"
            print(f"      {status} {rel_type} {count_str}")

        print()

    # Namespace breakdown
    print("📦 NAMESPACE BREAKDOWN")
    print("-" * 80)

    def get_usage_count(item: tuple[str, dict]) -> int:
        return item[1]["usage_count"]

    for namespace, stats in sorted(
        metrics["namespaces"].items(), key=get_usage_count, reverse=True
    ):
        active_pct = (stats["active"] / stats["total"] * 100) if stats["total"] > 0 else 0
        print(
            f"  {namespace:10s}: {stats['active']:2d}/{stats['total']:2d} active "
            f"({active_pct:5.1f}%), {stats['usage_count']:6d} total uses"
        )

    print()

    # Top 10 most used
    print("🔥 TOP 10 MOST USED RELATIONSHIPS")
    print("-" * 80)

    for i, rel in enumerate(metrics["top_10_used"], 1):
        print(f"  {i:2d}. {rel['type']:50s} ({rel['count']:6d} uses)")

    print()

    # Recommendations
    print("💡 RECOMMENDATIONS")
    print("-" * 80)

    tier_1_remaining = metrics["tier_1"]["target"] - metrics["tier_1"]["active"]
    tier_2_remaining = metrics["tier_2"]["target"] - metrics["tier_2"]["active"]

    if tier_1_remaining > 0:
        print(f"  🚀 PRIORITY: Implement {tier_1_remaining} remaining Tier 1 relationships")
        print("     These are high-impact, easy wins!")
        print()

    if tier_1_remaining == 0 and tier_2_remaining > 0:
        print(f"  ✅ Tier 1 Complete! Now focus on {tier_2_remaining} Tier 2 relationships")
        print()

    if tier_1_remaining == 0 and tier_2_remaining == 0:
        print("  🎉 Tiers 1-2 Complete! Consider Tier 3 advanced relationships")
        print()

    if metrics["activation_percentage"] < 20:
        print("  ⚠️  Activation below 20% - focus on quick wins (Tier 1)")
    elif metrics["activation_percentage"] < 40:
        print("  📈 Good progress! Continue with Tier 2 implementation")
    else:
        print("  🌟 Excellent activation! Graph intelligence is rich")

    print()
    print("=" * 80)


def print_detailed_unused(metrics: dict):
    """Print detailed list of unused semantic relationships."""

    print("\n" + "=" * 80)
    print("UNUSED SEMANTIC RELATIONSHIPS")
    print("=" * 80)
    print(f"Total Unused: {metrics['unused_count']}")
    print()

    # Group by tier
    tier_1_unused = [r for r in metrics["unused_types"] if r in TIER_1_RELATIONSHIPS]
    tier_2_unused = [r for r in metrics["unused_types"] if r in TIER_2_RELATIONSHIPS]
    tier_3_unused = [r for r in metrics["unused_types"] if r in TIER_3_RELATIONSHIPS]
    other_unused = [
        r
        for r in metrics["unused_types"]
        if r not in TIER_1_RELATIONSHIPS + TIER_2_RELATIONSHIPS + TIER_3_RELATIONSHIPS
    ]

    if tier_1_unused:
        print("🔴 TIER 1 UNUSED (Implement First!):")
        for rel in tier_1_unused:
            print(f"  - {rel}")
        print()

    if tier_2_unused:
        print("🟡 TIER 2 UNUSED (Implement Second):")
        for rel in tier_2_unused:
            print(f"  - {rel}")
        print()

    if tier_3_unused:
        print("🔵 TIER 3 UNUSED (Future Work):")
        for rel in tier_3_unused:
            print(f"  - {rel}")
        print()

    if other_unused:
        print("⚪ OTHER UNUSED:")
        for rel in other_unused:
            print(f"  - {rel}")
        print()


async def main():
    """Main entry point."""
    import sys

    # Parse simple args
    detailed = "--detailed" in sys.argv
    export_file = None

    if "--export" in sys.argv:
        idx = sys.argv.index("--export")
        if idx + 1 < len(sys.argv):
            export_file = sys.argv[idx + 1]

    print("Fetching semantic relationship metrics from Neo4j...")

    try:
        metrics = await get_semantic_relationship_metrics()

        # Print summary
        print_metrics_summary(metrics)

        # Print detailed unused if requested
        if detailed:
            print_detailed_unused(metrics)

        # Export to JSON if requested
        if export_file:
            output_path = Path(export_file)
            output_path.write_text(json.dumps(metrics, indent=2))
            print(f"\n✅ Metrics exported to: {output_path}")

        # Exit code based on Tier 1 completion
        tier_1_complete = metrics["tier_1"]["active"] == metrics["tier_1"]["target"]
        return 0 if tier_1_complete else 1

    except Exception as e:
        print(f"\n❌ Error fetching metrics: {e}")
        import traceback

        traceback.print_exc()
        return 2


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
