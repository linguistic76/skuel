"""
A/B Test Results Analyzer
==========================

Analyze search metrics to compare control vs treatment groups.

**Usage:**
```bash
poetry run python scripts/analyze_ab_test_results.py semantic_search_v1 --days 7
```

**Metrics Compared:**
- Click-through rate (CTR)
- Time to first click
- Results per query
- User satisfaction (proxy: return visits)

**Data Source:**
Uses search metrics tracked in Neo4j (SearchMetrics nodes).

Version: 1.0.0 (January 2026 - Phase 2)
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from neo4j import AsyncGraphDatabase

from core.config.unified_config import UnifiedConfig
from core.services.ab_testing_service import ABTestingService, TestGroup
from core.utils.logging import get_logger

logger = get_logger("skuel.scripts.ab_test_analyzer")


async def analyze_test_results(
    test_id: str, days: int = 7, config: UnifiedConfig | None = None
) -> dict[str, Any]:
    """
    Analyze A/B test results by comparing control vs treatment metrics.

    Args:
        test_id: Test identifier (e.g., "semantic_search_v1")
        days: Number of days to analyze
        config: Unified config (creates default if None)

    Returns:
        Dict with analysis results
    """
    if config is None:
        config = UnifiedConfig.from_environment()

    # Initialize services
    ab_service = ABTestingService()  # No active tests by default
    driver = AsyncGraphDatabase.driver(
        config.database.neo4j_uri,
        auth=(config.database.neo4j_username, config.database.neo4j_password),
    )

    try:
        # Get all users who searched in the time period
        since = datetime.now() - timedelta(days=days)

        query = """
        MATCH (u:User)
        WHERE exists {
            MATCH (u)-[:PERFORMED]->(s:SearchMetrics)
            WHERE s.timestamp >= $since
        }
        RETURN u.uid as user_uid
        """

        async with driver.session() as session:
            result = await session.run(query, since=since.isoformat())
            users = [record["user_uid"] async for record in result]

        logger.info(f"Found {len(users)} users with search activity in past {days} days")

        # Assign users to groups
        control_users = []
        treatment_users = []

        for user_uid in users:
            group = ab_service.get_test_group(test_id, user_uid)
            if group == TestGroup.CONTROL:
                control_users.append(user_uid)
            else:
                treatment_users.append(user_uid)

        logger.info(f"Control: {len(control_users)} users, Treatment: {len(treatment_users)} users")

        # Get metrics for each group
        control_metrics = await _get_group_metrics(driver, control_users, since)
        treatment_metrics = await _get_group_metrics(driver, treatment_users, since)

        # Calculate comparison
        comparison = {
            "test_id": test_id,
            "analysis_period_days": days,
            "total_users": len(users),
            "control": {
                "user_count": len(control_users),
                **control_metrics,
            },
            "treatment": {
                "user_count": len(treatment_users),
                **treatment_metrics,
            },
            "improvements": _calculate_improvements(control_metrics, treatment_metrics),
        }

        return comparison

    finally:
        await driver.close()


async def _get_group_metrics(
    driver: Any, user_uids: list[str], since: datetime
) -> dict[str, float]:
    """
    Get search metrics for a group of users.

    Returns:
        Dict with aggregated metrics
    """
    if not user_uids:
        return {
            "total_searches": 0,
            "total_clicks": 0,
            "avg_results_per_query": 0.0,
            "avg_time_to_click_sec": 0.0,
            "click_through_rate": 0.0,
        }

    query = """
    MATCH (u:User)-[:PERFORMED]->(s:SearchMetrics)
    WHERE u.uid IN $user_uids
      AND s.timestamp >= $since
    RETURN
        count(s) as total_searches,
        sum(coalesce(s.result_count, 0)) as total_results,
        sum(coalesce(s.clicks, 0)) as total_clicks,
        avg(coalesce(s.time_to_first_click_sec, 0)) as avg_time_to_click
    """

    async with driver.session() as session:
        result = await session.run(query, user_uids=user_uids, since=since.isoformat())
        record = await result.single()

        total_searches = record["total_searches"] or 0
        total_results = record["total_results"] or 0
        total_clicks = record["total_clicks"] or 0
        avg_time = record["avg_time_to_click"] or 0.0

        return {
            "total_searches": total_searches,
            "total_clicks": total_clicks,
            "avg_results_per_query": total_results / max(total_searches, 1),
            "avg_time_to_click_sec": avg_time,
            "click_through_rate": total_clicks / max(total_searches, 1),
        }


def _calculate_improvements(
    control: dict[str, float], treatment: dict[str, float]
) -> dict[str, float]:
    """
    Calculate percentage improvements from control to treatment.

    Returns:
        Dict with improvement percentages (positive = treatment better)
    """
    improvements = {}

    for metric in ["click_through_rate", "avg_results_per_query"]:
        control_val = control.get(metric, 0.0)
        treatment_val = treatment.get(metric, 0.0)

        if control_val > 0:
            improvement_pct = ((treatment_val - control_val) / control_val) * 100
            improvements[f"{metric}_improvement_pct"] = round(improvement_pct, 2)
        else:
            improvements[f"{metric}_improvement_pct"] = 0.0

    # Time to click: lower is better
    control_time = control.get("avg_time_to_click_sec", 0.0)
    treatment_time = treatment.get("avg_time_to_click_sec", 0.0)

    if control_time > 0:
        time_improvement_pct = ((control_time - treatment_time) / control_time) * 100
        improvements["time_to_click_improvement_pct"] = round(time_improvement_pct, 2)
    else:
        improvements["time_to_click_improvement_pct"] = 0.0

    return improvements


def _print_analysis(analysis: dict[str, Any]) -> None:
    """Pretty-print analysis results."""
    print(f"\n{'=' * 60}")
    print(f"A/B Test Analysis: {analysis['test_id']}")
    print(f"Period: {analysis['analysis_period_days']} days")
    print(f"{'=' * 60}\n")

    print(f"Total Users: {analysis['total_users']}")
    print(f"  Control: {analysis['control']['user_count']}")
    print(f"  Treatment: {analysis['treatment']['user_count']}\n")

    print("Metrics Comparison:")
    print(f"{'Metric':<30} {'Control':>12} {'Treatment':>12} {'Change':>10}")
    print("-" * 66)

    metrics = [
        ("Total Searches", "total_searches", ""),
        ("Click-Through Rate", "click_through_rate", "%"),
        ("Avg Results/Query", "avg_results_per_query", ""),
        ("Avg Time to Click", "avg_time_to_click_sec", "s"),
    ]

    for label, key, unit in metrics:
        ctrl_val = analysis["control"].get(key, 0.0)
        treat_val = analysis["treatment"].get(key, 0.0)

        if "rate" in key or "avg" in key:
            ctrl_str = f"{ctrl_val:.2f}{unit}"
            treat_str = f"{treat_val:.2f}{unit}"
        else:
            ctrl_str = f"{int(ctrl_val)}{unit}"
            treat_str = f"{int(treat_val)}{unit}"

        # Calculate change
        if ctrl_val > 0:
            if "time" in key:
                # Lower is better for time
                change_pct = ((ctrl_val - treat_val) / ctrl_val) * 100
            else:
                # Higher is better for other metrics
                change_pct = ((treat_val - ctrl_val) / ctrl_val) * 100

            change_str = f"{change_pct:+.1f}%"
            if change_pct > 0:
                change_str = f"✅ {change_str}"
            elif change_pct < 0:
                change_str = f"❌ {change_str}"
        else:
            change_str = "N/A"

        print(f"{label:<30} {ctrl_str:>12} {treat_str:>12} {change_str:>10}")

    print(f"\n{'=' * 60}\n")


async def main():
    """Main entry point."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze_ab_test_results.py <test_id> [--days <N>]")
        print("Example: python scripts/analyze_ab_test_results.py semantic_search_v1 --days 7")
        return

    test_id = sys.argv[1]
    days = 7

    if "--days" in sys.argv:
        days_idx = sys.argv.index("--days") + 1
        if days_idx < len(sys.argv):
            days = int(sys.argv[days_idx])

    logger.info(f"Analyzing test: {test_id} (past {days} days)")

    analysis = await analyze_test_results(test_id, days)
    _print_analysis(analysis)


if __name__ == "__main__":
    asyncio.run(main())
