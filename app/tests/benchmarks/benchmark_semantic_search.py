"""
Performance benchmarking for semantic-enhanced search.

Measures latency and throughput for:
1. Standard vector search (baseline)
2. Semantic-enhanced search
3. Learning-aware search
4. Hybrid search

Usage:
    poetry run python tests/benchmarks/benchmark_semantic_search.py

Output:
    - Latency statistics (mean, p50, p95, p99)
    - Throughput (queries per second)
    - Comparison tables
"""

import asyncio
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass

from neo4j import AsyncGraphDatabase

from core.config.unified_config import VectorSearchConfig
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService


@dataclass
class BenchmarkResult:
    """Results from a benchmark run."""

    name: str
    iterations: int
    latencies_ms: list[float]
    mean_ms: float
    median_ms: float
    p95_ms: float
    p99_ms: float
    qps: float  # Queries per second

    def __str__(self) -> str:
        return (
            f"{self.name:40} | "
            f"Mean: {self.mean_ms:6.2f}ms | "
            f"P50: {self.median_ms:6.2f}ms | "
            f"P95: {self.p95_ms:6.2f}ms | "
            f"P99: {self.p99_ms:6.2f}ms | "
            f"QPS: {self.qps:6.1f}"
        )


async def benchmark_function(
    func: Callable, iterations: int = 100, warmup: int = 10
) -> list[float]:
    """Benchmark a function and return latency measurements."""

    latencies = []

    # Warmup runs
    for _ in range(warmup):
        await func()

    # Actual benchmark runs
    for _ in range(iterations):
        start = time.perf_counter()
        await func()
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)

    return latencies


def calculate_stats(name: str, latencies_ms: list[float], iterations: int) -> BenchmarkResult:
    """Calculate benchmark statistics."""

    mean_ms = statistics.mean(latencies_ms)
    median_ms = statistics.median(latencies_ms)

    sorted_latencies = sorted(latencies_ms)
    p95_idx = int(len(sorted_latencies) * 0.95)
    p99_idx = int(len(sorted_latencies) * 0.99)

    p95_ms = sorted_latencies[p95_idx]
    p99_ms = sorted_latencies[p99_idx]

    # Queries per second (using mean latency)
    qps = 1000.0 / mean_ms if mean_ms > 0 else 0

    return BenchmarkResult(
        name=name,
        iterations=iterations,
        latencies_ms=latencies_ms,
        mean_ms=mean_ms,
        median_ms=median_ms,
        p95_ms=p95_ms,
        p99_ms=p99_ms,
        qps=qps,
    )


async def setup_benchmark_data(driver):
    """Create test data for benchmarking."""

    async with driver.session() as session:
        # Create 100 test KUs with embeddings
        for i in range(100):
            await session.run(
                """
                CREATE (k:Ku {
                    uid: $uid,
                    title: $title,
                    description: $description,
                    embedding: $embedding,
                    created_at: datetime()
                })
            """,
                uid=f"ku.bench-{i}",
                title=f"Benchmark KU {i}",
                description=f"Test knowledge unit {i} for benchmarking",
                embedding=[0.01 * i] * 1536,
            )

        # Create semantic relationships (20% of KUs have relationships)
        for i in range(0, 100, 5):
            target = i
            source = (i + 1) % 100
            await session.run(
                """
                MATCH (k1:Ku {uid: $target_uid})
                MATCH (k2:Ku {uid: $source_uid})
                CREATE (k1)-[:REQUIRES_THEORETICAL_UNDERSTANDING {
                    confidence: 0.8,
                    strength: 1.0,
                    source: 'benchmark'
                }]->(k2)
            """,
                target_uid=f"ku.bench-{target}",
                source_uid=f"ku.bench-{source}",
            )

        # Create test user and learning states
        await session.run("""
            CREATE (u:User {uid: 'user.benchmark', created_at: datetime()})
        """)

        # Create learning states (1/3 mastered, 1/3 in_progress, 1/3 none)
        for i in range(0, 100, 3):
            # Mastered
            await session.run(
                """
                MATCH (u:User {uid: 'user.benchmark'})
                MATCH (k:Ku {uid: $uid})
                CREATE (u)-[:MASTERED {mastered_at: datetime()}]->(k)
            """,
                uid=f"ku.bench-{i}",
            )

        for i in range(1, 100, 3):
            # In progress
            await session.run(
                """
                MATCH (u:User {uid: 'user.benchmark'})
                MATCH (k:Ku {uid: $uid})
                CREATE (u)-[:IN_PROGRESS {started_at: datetime()}]->(k)
            """,
                uid=f"ku.bench-{i}",
            )


async def cleanup_benchmark_data(driver):
    """Clean up test data after benchmarking."""

    async with driver.session() as session:
        # Delete test KUs and user
        await session.run("""
            MATCH (k:Ku)
            WHERE k.uid STARTS WITH 'ku.bench-'
            DETACH DELETE k
        """)
        await session.run("""
            MATCH (u:User {uid: 'user.benchmark'})
            DETACH DELETE u
        """)


async def run_benchmarks():
    """Run all benchmark tests."""

    # Connect to Neo4j (assumes local instance running)
    driver = AsyncGraphDatabase.driver(
        "neo4j://localhost:7687",
        auth=("neo4j", "password"),  # Update with your credentials
    )

    # Mock embeddings service
    class MockEmbeddingsService:
        async def create_embedding(self, text):
            from core.utils.result_simplified import Result

            return Result.ok([0.1] * 1536)

    embeddings_service = MockEmbeddingsService()
    config = VectorSearchConfig(ku_min_score=0.0)

    vector_search = Neo4jVectorSearchService(
        driver=driver, embeddings_service=embeddings_service, config=config
    )

    try:
        print("Setting up benchmark data...")
        await setup_benchmark_data(driver)

        print("Running benchmarks (100 iterations each)...\n")

        iterations = 100
        results = []

        # Benchmark 1: Standard vector search (baseline)
        print("1/4: Benchmarking standard vector search...")

        async def standard_search():
            await vector_search.find_similar_by_text(label="Ku", text="benchmark test", limit=10)

        latencies = await benchmark_function(standard_search, iterations)
        results.append(calculate_stats("Standard vector search", latencies, iterations))

        # Benchmark 2: Semantic-enhanced search
        print("2/4: Benchmarking semantic-enhanced search...")

        async def semantic_search():
            await vector_search.semantic_enhanced_search(
                label="Ku",
                text="benchmark test",
                context_uids=[f"ku.bench-{i}" for i in range(10)],
                limit=10,
            )

        latencies = await benchmark_function(semantic_search, iterations)
        results.append(calculate_stats("Semantic-enhanced search", latencies, iterations))

        # Benchmark 3: Learning-aware search
        print("3/4: Benchmarking learning-aware search...")

        async def learning_search():
            await vector_search.learning_aware_search(
                label="Ku",
                text="benchmark test",
                user_uid="user.benchmark",
                prefer_unmastered=True,
                limit=10,
            )

        latencies = await benchmark_function(learning_search, iterations)
        results.append(calculate_stats("Learning-aware search", latencies, iterations))

        # Benchmark 4: Hybrid search
        print("4/4: Benchmarking hybrid search...")

        async def hybrid_search_func():
            await vector_search.hybrid_search(label="Ku", query_text="benchmark test", limit=10)

        latencies = await benchmark_function(hybrid_search_func, iterations)
        results.append(calculate_stats("Hybrid search (RRF)", latencies, iterations))

        # Print results
        print("\n" + "=" * 120)
        print("BENCHMARK RESULTS")
        print("=" * 120)
        print(
            f"{'Method':<40} | {'Mean':>10} | {'P50':>10} | {'P95':>10} | {'P99':>10} | {'QPS':>10}"
        )
        print("-" * 120)

        for result in results:
            print(result)

        # Calculate overhead
        baseline = results[0]  # Standard vector search
        semantic = results[1]
        learning = results[2]
        hybrid = results[3]

        print("\n" + "=" * 120)
        print("OVERHEAD ANALYSIS")
        print("=" * 120)

        semantic_overhead = semantic.mean_ms - baseline.mean_ms
        learning_overhead = learning.mean_ms - baseline.mean_ms
        hybrid_overhead = hybrid.mean_ms - baseline.mean_ms

        print(
            f"Semantic-enhanced overhead: {semantic_overhead:+6.2f}ms "
            f"({(semantic_overhead / baseline.mean_ms * 100):+5.1f}%)"
        )
        print(
            f"Learning-aware overhead:    {learning_overhead:+6.2f}ms "
            f"({(learning_overhead / baseline.mean_ms * 100):+5.1f}%)"
        )
        print(
            f"Hybrid search overhead:     {hybrid_overhead:+6.2f}ms "
            f"({(hybrid_overhead / baseline.mean_ms * 100):+5.1f}%)"
        )

        # Performance targets
        print("\n" + "=" * 120)
        print("PERFORMANCE TARGETS")
        print("=" * 120)

        def check_target(result: BenchmarkResult, target_ms: float) -> str:
            status = "✓ PASS" if result.p95_ms < target_ms else "✗ FAIL"
            return f"{status} (P95: {result.p95_ms:.2f}ms, Target: <{target_ms}ms)"

        print(f"Standard vector search:     {check_target(baseline, 150)}")
        print(f"Semantic-enhanced search:   {check_target(semantic, 200)}")
        print(f"Learning-aware search:      {check_target(learning, 180)}")
        print(f"Hybrid search:              {check_target(hybrid, 250)}")

    finally:
        print("\nCleaning up benchmark data...")
        await cleanup_benchmark_data(driver)
        await driver.close()


if __name__ == "__main__":
    print("Semantic Search Performance Benchmark")
    print("=" * 120)
    print()
    asyncio.run(run_benchmarks())
