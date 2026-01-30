#!/usr/bin/env python3
"""
Analyze Search Metrics from Logs
=================================

Parses application logs to extract and analyze search metrics.

Generates reports on:
- Search performance (latency distribution)
- Search quality (similarity scores)
- Query patterns (most common searches)
- Entity type distribution

Usage:
    poetry run python scripts/analyze_search_metrics.py logs/skuel.log
    poetry run python scripts/analyze_search_metrics.py logs/skuel.log --top 20
    poetry run python scripts/analyze_search_metrics.py logs/skuel.log --type hybrid
    poetry run python scripts/analyze_search_metrics.py logs/skuel.log --label Ku

Created: January 2026
See: /docs/architecture/SEARCH_ARCHITECTURE.md
"""

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from core.models.semantic import SearchMetricsAggregate


def parse_log_line(line: str) -> dict[str, Any] | None:
    """
    Parse a search metrics log line.

    Expected format:
    2026-01-29 12:34:56 [info] Search metrics: query='python' type=hybrid label=Ku results=10 avg_score=0.850 latency=45.2ms

    Args:
        line: Log line to parse

    Returns:
        Dict with parsed metrics or None if not a metrics line
    """
    # Pattern to match search metrics log lines
    pattern = r"Search metrics: query='([^']+)' type=(\w+) label=(\w+) results=(\d+) avg_score=([\d.]+) latency=([\d.]+)ms"

    match = re.search(pattern, line)
    if not match:
        return None

    query, search_type, label, results, avg_score, latency = match.groups()

    return {
        "query": query,
        "search_type": search_type,
        "label": label,
        "num_results": int(results),
        "avg_similarity": float(avg_score),
        "latency_ms": float(latency),
    }


def calculate_percentile(values: list[float], percentile: int) -> float:
    """
    Calculate percentile from sorted values.

    Args:
        values: Sorted list of values
        percentile: Percentile to calculate (0-100)

    Returns:
        Percentile value
    """
    if not values:
        return 0.0

    index = int(len(values) * percentile / 100)
    # Clamp to valid index range
    index = max(0, min(index, len(values) - 1))
    return values[index]


def analyze_metrics(metrics_list: list[dict[str, Any]]) -> SearchMetricsAggregate:
    """
    Analyze search metrics and generate aggregate statistics.

    Args:
        metrics_list: List of parsed metrics dicts

    Returns:
        SearchMetricsAggregate with statistics
    """
    if not metrics_list:
        return SearchMetricsAggregate(
            total_queries=0,
            avg_latency_ms=0.0,
            avg_results_per_query=0.0,
            avg_similarity=0.0,
            queries_by_type={},
            queries_by_label={},
            p50_latency_ms=0.0,
            p95_latency_ms=0.0,
            p99_latency_ms=0.0,
        )

    total_queries = len(metrics_list)

    # Calculate averages
    avg_latency_ms = sum(m["latency_ms"] for m in metrics_list) / total_queries
    avg_results_per_query = sum(m["num_results"] for m in metrics_list) / total_queries
    avg_similarity = sum(m["avg_similarity"] for m in metrics_list) / total_queries

    # Count by type and label
    queries_by_type = Counter(m["search_type"] for m in metrics_list)
    queries_by_label = Counter(m["label"] for m in metrics_list)

    # Calculate latency percentiles
    latencies = sorted([m["latency_ms"] for m in metrics_list])
    p50_latency_ms = calculate_percentile(latencies, 50)
    p95_latency_ms = calculate_percentile(latencies, 95)
    p99_latency_ms = calculate_percentile(latencies, 99)

    return SearchMetricsAggregate(
        total_queries=total_queries,
        avg_latency_ms=avg_latency_ms,
        avg_results_per_query=avg_results_per_query,
        avg_similarity=avg_similarity,
        queries_by_type=dict(queries_by_type),
        queries_by_label=dict(queries_by_label),
        p50_latency_ms=p50_latency_ms,
        p95_latency_ms=p95_latency_ms,
        p99_latency_ms=p99_latency_ms,
    )


def get_top_queries(metrics_list: list[dict[str, Any]], top_n: int = 10) -> list[tuple[str, int]]:
    """
    Get most common queries.

    Args:
        metrics_list: List of parsed metrics
        top_n: Number of top queries to return

    Returns:
        List of (query, count) tuples
    """
    query_counts = Counter(m["query"] for m in metrics_list)
    return query_counts.most_common(top_n)


def get_slow_queries(
    metrics_list: list[dict[str, Any]], threshold_ms: float = 200.0
) -> list[dict[str, Any]]:
    """
    Get queries that exceeded latency threshold.

    Args:
        metrics_list: List of parsed metrics
        threshold_ms: Latency threshold in milliseconds

    Returns:
        List of slow queries sorted by latency (slowest first)
    """
    slow = [m for m in metrics_list if m["latency_ms"] > threshold_ms]
    return sorted(slow, key=lambda x: x["latency_ms"], reverse=True)


def analyze_by_type(metrics_list: list[dict[str, Any]]) -> dict[str, SearchMetricsAggregate]:
    """
    Analyze metrics grouped by search type.

    Args:
        metrics_list: List of parsed metrics

    Returns:
        Dict mapping search_type -> SearchMetricsAggregate
    """
    by_type = defaultdict(list)
    for m in metrics_list:
        by_type[m["search_type"]].append(m)

    return {search_type: analyze_metrics(metrics) for search_type, metrics in by_type.items()}


def analyze_by_label(metrics_list: list[dict[str, Any]]) -> dict[str, SearchMetricsAggregate]:
    """
    Analyze metrics grouped by entity label.

    Args:
        metrics_list: List of parsed metrics

    Returns:
        Dict mapping label -> SearchMetricsAggregate
    """
    by_label = defaultdict(list)
    for m in metrics_list:
        by_label[m["label"]].append(m)

    return {label: analyze_metrics(metrics) for label, metrics in by_label.items()}


def print_report(
    aggregate: SearchMetricsAggregate,
    top_queries: list[tuple[str, int]],
    slow_queries: list[dict[str, Any]],
    by_type: dict[str, SearchMetricsAggregate],
    by_label: dict[str, SearchMetricsAggregate],
):
    """
    Print comprehensive analysis report.

    Args:
        aggregate: Overall aggregate metrics
        top_queries: Most common queries
        slow_queries: Slowest queries
        by_type: Metrics grouped by search type
        by_label: Metrics grouped by label
    """
    print("=" * 80)
    print("SEARCH METRICS ANALYSIS REPORT")
    print("=" * 80)
    print()

    # Overall summary
    print(aggregate.summary())
    print()

    # Top queries
    print("-" * 80)
    print(f"TOP {len(top_queries)} QUERIES")
    print("-" * 80)
    for i, (query, count) in enumerate(top_queries, 1):
        print(f"{i:2d}. {query[:60]:60s} ({count} queries)")
    print()

    # Slow queries
    if slow_queries:
        print("-" * 80)
        print(f"SLOW QUERIES (>{slow_queries[0]['latency_ms']:.0f}ms threshold)")
        print("-" * 80)
        for i, sq in enumerate(slow_queries[:10], 1):
            print(
                f"{i:2d}. {sq['query'][:50]:50s} {sq['latency_ms']:6.1f}ms ({sq['search_type']} on {sq['label']})"
            )
        print()

    # By search type
    print("-" * 80)
    print("METRICS BY SEARCH TYPE")
    print("-" * 80)
    for search_type, stats in sorted(by_type.items()):
        print(f"\n{search_type.upper()}:")
        print(f"  Queries: {stats.total_queries}")
        print(f"  Avg Latency: {stats.avg_latency_ms:.1f}ms (p95={stats.p95_latency_ms:.1f}ms)")
        print(f"  Avg Results: {stats.avg_results_per_query:.1f}")
        print(f"  Avg Similarity: {stats.avg_similarity:.3f}")
    print()

    # By label
    print("-" * 80)
    print("METRICS BY ENTITY LABEL")
    print("-" * 80)
    for label, stats in sorted(by_label.items()):
        print(f"\n{label}:")
        print(f"  Queries: {stats.total_queries}")
        print(f"  Avg Latency: {stats.avg_latency_ms:.1f}ms (p95={stats.p95_latency_ms:.1f}ms)")
        print(f"  Avg Results: {stats.avg_results_per_query:.1f}")
        print(f"  Avg Similarity: {stats.avg_similarity:.3f}")
    print()

    print("=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze search metrics from application logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze all metrics in log file
  poetry run python scripts/analyze_search_metrics.py logs/skuel.log

  # Show top 20 queries
  poetry run python scripts/analyze_search_metrics.py logs/skuel.log --top 20

  # Filter by search type
  poetry run python scripts/analyze_search_metrics.py logs/skuel.log --type hybrid

  # Filter by entity label
  poetry run python scripts/analyze_search_metrics.py logs/skuel.log --label Ku

  # Set slow query threshold
  poetry run python scripts/analyze_search_metrics.py logs/skuel.log --slow 100
        """,
    )

    parser.add_argument("log_file", help="Path to log file to analyze")
    parser.add_argument(
        "--top", type=int, default=10, help="Number of top queries to show (default: 10)"
    )
    parser.add_argument("--type", help="Filter by search type (vector, fulltext, hybrid)")
    parser.add_argument("--label", help="Filter by entity label (Ku, Task, Goal, etc.)")
    parser.add_argument(
        "--slow", type=float, default=200.0, help="Slow query threshold in ms (default: 200)"
    )

    args = parser.parse_args()

    # Check log file exists
    log_path = Path(args.log_file)
    if not log_path.exists():
        print(f"Error: Log file not found: {args.log_file}", file=sys.stderr)
        return 1

    # Parse log file
    print(f"Parsing log file: {args.log_file}")
    metrics_list = []

    with open(log_path) as f:
        for line in f:
            metrics = parse_log_line(line)
            if metrics:
                # Apply filters
                if args.type and metrics["search_type"] != args.type:
                    continue
                if args.label and metrics["label"] != args.label:
                    continue

                metrics_list.append(metrics)

    if not metrics_list:
        print("No search metrics found in log file.")
        print(
            "Make sure the application is using find_similar_with_metrics() or hybrid_search_with_metrics()"
        )
        return 1

    print(f"Found {len(metrics_list)} search metric entries")
    print()

    # Analyze
    aggregate = analyze_metrics(metrics_list)
    top_queries = get_top_queries(metrics_list, args.top)
    slow_queries = get_slow_queries(metrics_list, args.slow)
    by_type = analyze_by_type(metrics_list)
    by_label = analyze_by_label(metrics_list)

    # Print report
    print_report(aggregate, top_queries, slow_queries, by_type, by_label)

    return 0


if __name__ == "__main__":
    sys.exit(main())
