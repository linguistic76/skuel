#!/usr/bin/env python3
"""
Benchmark Embedding Cache Performance
======================================

Measures cache hit rate and performance improvements from embedding caching.

Compares:
- Cache-first approach (get_or_create_embedding)
- Always-generate approach (create_embedding)

Metrics:
- Cache hit rate
- API calls saved
- Average latency (cached vs uncached)
- Cost savings estimate

Usage:
    uv run python scripts/benchmark_embedding_cache.py --sample 100
    uv run python scripts/benchmark_embedding_cache.py --label Ku
    uv run python scripts/benchmark_embedding_cache.py --verbose

Created: January 2026
See: /docs/architecture/SEARCH_ARCHITECTURE.md
"""

import argparse
import asyncio
import sys
import time
from collections import defaultdict

from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection
from core.services.embeddings_service import (
    EMBEDDING_VERSION,
    HuggingFaceEmbeddingsService,
)
from core.utils.logging import get_logger

logger = get_logger("skuel.scripts.cache_benchmark")


async def get_sample_nodes(driver, label: str | None = None, limit: int = 100) -> list[dict]:
    """
    Get sample nodes with text content for benchmarking.

    Args:
        driver: Neo4j driver
        label: Optional label filter
        limit: Number of nodes to sample

    Returns:
        List of node records
    """
    label_clause = f":{label}" if label else ""

    query = f"""
    MATCH (n{label_clause})
    WHERE n.embedding IS NOT NULL
      AND (n.title IS NOT NULL OR n.content IS NOT NULL OR n.description IS NOT NULL)
    RETURN labels(n)[0] as label,
           n.uid as uid,
           coalesce(n.title, n.name, n.statement, '') as title,
           coalesce(n.content, n.description, '') as content,
           n.embedding_version as version
    ORDER BY rand()
    LIMIT $limit
    """

    try:
        result = await driver.execute_query(query, {"limit": limit})
        return [dict(record) for record in result]
    except Exception as e:
        logger.error(f"Failed to get sample nodes: {e}")
        return []


def get_text_from_node(node: dict) -> str:
    """Extract text from node for embedding."""
    title = node.get("title", "").strip()
    content = node.get("content", "").strip()

    if title and content:
        return f"{title}\n\n{content}"
    elif title:
        return title
    elif content:
        return content
    else:
        return node.get("uid", "")


async def benchmark_cache_first(
    service: HuggingFaceEmbeddingsService,
    nodes: list[dict],
    verbose: bool = False,
) -> dict:
    """
    Benchmark cache-first approach.

    Args:
        service: Embeddings service
        nodes: Sample nodes
        verbose: Show detailed output

    Returns:
        Benchmark results
    """
    logger.info(f"Benchmarking cache-first approach on {len(nodes)} nodes...")

    cache_hits = 0
    cache_misses = 0
    total_latency = 0.0
    cached_latency = 0.0
    uncached_latency = 0.0
    errors = 0

    by_label = defaultdict(lambda: {"hits": 0, "misses": 0})

    for i, node in enumerate(nodes, 1):
        uid = node["uid"]
        label = node["label"]
        text = get_text_from_node(node)

        # Check if node has current version (to predict cache hit)
        has_current = node.get("version") == EMBEDDING_VERSION

        start = time.perf_counter()

        result = await service.get_or_create_embedding(
            uid=uid,
            label=label,
            text=text,
        )

        latency = (time.perf_counter() - start) * 1000
        total_latency += latency

        if result.is_error:
            errors += 1
            if verbose:
                logger.warning(f"Error on {label}:{uid}: {result.error}")
            continue

        # Classify as cache hit or miss based on latency
        # Cache hits are typically < 10ms, API calls > 50ms
        is_cache_hit = latency < 20.0 or has_current

        if is_cache_hit:
            cache_hits += 1
            cached_latency += latency
            by_label[label]["hits"] += 1
        else:
            cache_misses += 1
            uncached_latency += latency
            by_label[label]["misses"] += 1

        if verbose and i % 10 == 0:
            logger.info(f"Progress: {i}/{len(nodes)} ({cache_hits} hits, {cache_misses} misses)")

    total_requests = cache_hits + cache_misses
    cache_hit_rate = (cache_hits / total_requests * 100) if total_requests > 0 else 0

    avg_cached = cached_latency / cache_hits if cache_hits > 0 else 0
    avg_uncached = uncached_latency / cache_misses if cache_misses > 0 else 0
    avg_total = total_latency / total_requests if total_requests > 0 else 0

    return {
        "total_requests": total_requests,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "cache_hit_rate": cache_hit_rate,
        "errors": errors,
        "total_latency_ms": total_latency,
        "avg_latency_ms": avg_total,
        "avg_cached_latency_ms": avg_cached,
        "avg_uncached_latency_ms": avg_uncached,
        "by_label": dict(by_label),
    }


async def benchmark_always_generate(
    service: HuggingFaceEmbeddingsService,
    nodes: list[dict],
    verbose: bool = False,
) -> dict:
    """
    Benchmark always-generate approach (no caching).

    Args:
        service: Embeddings service
        nodes: Sample nodes (limited to avoid excessive API calls)
        verbose: Show detailed output

    Returns:
        Benchmark results
    """
    # Limit to 10 nodes to avoid excessive API costs
    sample_nodes = nodes[:10]
    logger.info(
        f"Benchmarking always-generate on {len(sample_nodes)} nodes (limited to save costs)..."
    )

    total_latency = 0.0
    successes = 0
    errors = 0

    for i, node in enumerate(sample_nodes, 1):
        text = get_text_from_node(node)

        start = time.perf_counter()

        result = await service.create_embedding(text)

        latency = (time.perf_counter() - start) * 1000
        total_latency += latency

        if result.is_error:
            errors += 1
            if verbose:
                logger.warning(f"Error on {node['uid']}: {result.error}")
        else:
            successes += 1

    total_requests = successes + errors
    avg_latency = total_latency / total_requests if total_requests > 0 else 0

    return {
        "total_requests": total_requests,
        "successes": successes,
        "errors": errors,
        "total_latency_ms": total_latency,
        "avg_latency_ms": avg_latency,
    }


def calculate_cost_savings(cache_results: dict, always_results: dict) -> dict:
    """
    Calculate cost savings from caching.

    Estimates API call volume saved by caching.
    HuggingFace Inference API pricing varies by plan; cost figures are illustrative.

    Args:
        cache_results: Cache-first benchmark results
        always_results: Always-generate benchmark results

    Returns:
        Cost analysis dict
    """
    cache_hit_rate = cache_results["cache_hit_rate"]

    # Estimate monthly usage (1000 searches/day)
    monthly_searches = 30 * 1000

    # Without caching: all searches generate embeddings
    without_cache_api_calls = monthly_searches

    # With caching: only cache misses generate embeddings
    with_cache_api_calls = int(monthly_searches * (1 - cache_hit_rate / 100))

    api_calls_saved = without_cache_api_calls - with_cache_api_calls
    api_calls_reduction_pct = (
        (api_calls_saved / without_cache_api_calls * 100) if without_cache_api_calls > 0 else 0
    )

    # Cost calculation (assuming 500 tokens per embedding)
    cost_per_1m_tokens = 0.02  # illustrative; HuggingFace pricing varies by plan
    tokens_per_embedding = 500

    cost_without_cache = (
        without_cache_api_calls * tokens_per_embedding / 1_000_000
    ) * cost_per_1m_tokens
    cost_with_cache = (with_cache_api_calls * tokens_per_embedding / 1_000_000) * cost_per_1m_tokens
    monthly_savings = cost_without_cache - cost_with_cache
    annual_savings = monthly_savings * 12

    # Latency improvement
    avg_without_cache = always_results["avg_latency_ms"]
    avg_with_cache = cache_results["avg_latency_ms"]
    latency_improvement = avg_without_cache - avg_with_cache
    latency_improvement_pct = (
        (latency_improvement / avg_without_cache * 100) if avg_without_cache > 0 else 0
    )

    return {
        "cache_hit_rate": cache_hit_rate,
        "monthly_searches": monthly_searches,
        "api_calls_without_cache": without_cache_api_calls,
        "api_calls_with_cache": with_cache_api_calls,
        "api_calls_saved": api_calls_saved,
        "api_calls_reduction_pct": api_calls_reduction_pct,
        "cost_without_cache": cost_without_cache,
        "cost_with_cache": cost_with_cache,
        "monthly_savings": monthly_savings,
        "annual_savings": annual_savings,
        "avg_latency_without_cache": avg_without_cache,
        "avg_latency_with_cache": avg_with_cache,
        "latency_improvement_ms": latency_improvement,
        "latency_improvement_pct": latency_improvement_pct,
    }


def print_report(cache_results: dict, always_results: dict, cost_analysis: dict):
    """
    Print benchmark report.

    Args:
        cache_results: Cache-first results
        always_results: Always-generate results
        cost_analysis: Cost savings analysis
    """
    print()
    print("=" * 80)
    print("EMBEDDING CACHE BENCHMARK REPORT")
    print("=" * 80)
    print()

    # Cache performance
    print("-" * 80)
    print("CACHE PERFORMANCE")
    print("-" * 80)
    print(f"Total requests: {cache_results['total_requests']}")
    print(f"Cache hits: {cache_results['cache_hits']} ({cache_results['cache_hit_rate']:.1f}%)")
    print(f"Cache misses: {cache_results['cache_misses']}")
    print(f"Errors: {cache_results['errors']}")
    print()

    # Latency comparison
    print("-" * 80)
    print("LATENCY COMPARISON")
    print("-" * 80)
    print(f"Cached requests:  {cache_results['avg_cached_latency_ms']:6.1f}ms average")
    print(f"Uncached requests: {cache_results['avg_uncached_latency_ms']:6.1f}ms average")
    print(f"Overall (cached):  {cache_results['avg_latency_ms']:6.1f}ms average")
    print(f"Always-generate:   {always_results['avg_latency_ms']:6.1f}ms average")
    print()
    print(
        f"Latency improvement: {cost_analysis['latency_improvement_ms']:.1f}ms "
        f"({cost_analysis['latency_improvement_pct']:.1f}% faster)"
    )
    print()

    # Cache hits by label
    print("-" * 80)
    print("CACHE HITS BY ENTITY TYPE")
    print("-" * 80)
    for label, stats in sorted(cache_results["by_label"].items()):
        total = stats["hits"] + stats["misses"]
        hit_rate = (stats["hits"] / total * 100) if total > 0 else 0
        print(f"{label:15s} {stats['hits']:3d}/{total:3d} hits ({hit_rate:5.1f}%)")
    print()

    # Cost savings
    print("-" * 80)
    print("COST ANALYSIS (Monthly @ 1000 searches/day)")
    print("-" * 80)
    print(f"Cache hit rate: {cost_analysis['cache_hit_rate']:.1f}%")
    print()
    print(f"API calls without caching: {cost_analysis['api_calls_without_cache']:,}")
    print(f"API calls with caching:    {cost_analysis['api_calls_with_cache']:,}")
    print(
        f"API calls saved:           {cost_analysis['api_calls_saved']:,} "
        f"({cost_analysis['api_calls_reduction_pct']:.1f}% reduction)"
    )
    print()
    print(f"Cost without caching: ${cost_analysis['cost_without_cache']:.2f}/month")
    print(f"Cost with caching:    ${cost_analysis['cost_with_cache']:.2f}/month")
    print(f"Monthly savings:      ${cost_analysis['monthly_savings']:.2f}")
    print(f"Annual savings:       ${cost_analysis['annual_savings']:.2f}")
    print()

    print("=" * 80)
    print()

    # Recommendations
    if cost_analysis["cache_hit_rate"] >= 80:
        print("✅ Excellent cache hit rate! Caching is highly effective.")
    elif cost_analysis["cache_hit_rate"] >= 60:
        print("✓ Good cache hit rate. Consider increasing embedding coverage.")
    else:
        print("⚠️  Low cache hit rate. Check:")
        print("   - Are embeddings being generated with correct version?")
        print("   - Are nodes being updated frequently (invalidating cache)?")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Benchmark embedding cache performance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Benchmark 100 random nodes
  uv run python scripts/benchmark_embedding_cache.py --sample 100

  # Benchmark specific entity type
  uv run python scripts/benchmark_embedding_cache.py --label Ku --sample 50

  # Verbose output
  uv run python scripts/benchmark_embedding_cache.py --verbose

Note: Always-generate test is limited to 10 nodes to avoid excessive API costs.
        """,
    )

    parser.add_argument(
        "--sample", type=int, default=100, help="Number of nodes to sample (default: 100)"
    )
    parser.add_argument("--label", help="Filter by entity label (e.g., Ku, Task)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")

    args = parser.parse_args()

    conn = Neo4jConnection()
    await conn.connect()
    driver = conn.driver

    try:
        await driver.verify_connectivity()
        logger.info("✅ Connected to Neo4j")

        # Create embeddings service
        service = HuggingFaceEmbeddingsService(driver)

        # Check embeddings service availability
        plugin_available = await service._check_plugin_availability()
        if not plugin_available:
            logger.error("❌ Embeddings service not available")
            logger.error("   Set HF_API_TOKEN and INTELLIGENCE_TIER=full in .env to run this benchmark")
            return 1

        # Get sample nodes
        logger.info(f"Getting sample of {args.sample} nodes...")
        nodes = await get_sample_nodes(driver, args.label, args.sample)

        if not nodes:
            logger.error("No nodes found with embeddings")
            return 1

        logger.info(f"Found {len(nodes)} nodes for benchmarking")
        print()

        # Run benchmarks
        cache_results = await benchmark_cache_first(service, nodes, args.verbose)
        always_results = await benchmark_always_generate(service, nodes, args.verbose)

        # Calculate cost savings
        cost_analysis = calculate_cost_savings(cache_results, always_results)

        # Print report
        print_report(cache_results, always_results, cost_analysis)

        return 0

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        await conn.close()
        logger.info("✅ Disconnected from Neo4j")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
