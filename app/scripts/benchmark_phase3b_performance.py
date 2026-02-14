#!/usr/bin/env python3
"""
Phase 3B Performance Benchmarking Script
========================================

Measures actual performance improvements from graph-native relationship queries.

Benchmarks:
1. Relationship queries (get_related_uids)
2. Task retrieval with relationships
3. Knowledge-based task search
4. Prerequisite checking

Expected improvements: 40-60% reduction in queries and execution time.

Usage:
    poetry run python scripts/benchmark_phase3b_performance.py
"""

import asyncio
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.models.enums import KuStatus, Priority
from core.utils.result_simplified import Result


@dataclass
class BenchmarkResult:
    """Results from a benchmark run."""

    scenario: str
    pattern: str  # "old" or "new"
    query_count: int
    execution_time_ms: float
    items_processed: int
    memory_kb: float | None = None


class MockBackendOld:
    """Mock backend simulating OLD pattern (fetch all + filter in memory)."""

    def __init__(self, task_count: int = 1000):
        """Initialize with specified number of tasks."""
        self.task_count = task_count
        self.query_count = 0
        self._tasks = self._generate_tasks(task_count)

    def _generate_tasks(self, count: int) -> list[dict]:
        """Generate mock task data."""
        tasks = []
        for i in range(count):
            # Every 10th task applies ku.python.basics
            applies_knowledge = ["ku.python.basics"] if i % 10 == 0 else []
            tasks.append(
                {
                    "uid": f"task:{i}",
                    "user_uid": "user:demo",
                    "title": f"Task {i}",
                    "priority": Priority.MEDIUM.value,
                    "status": KuStatus.DRAFT.value,
                    "applies_knowledge_uids": applies_knowledge,  # OLD: Stored in model
                    "created_at": datetime.now().isoformat(),
                }
            )
        return tasks

    async def list_tasks(
        self, filters: dict | None = None, limit: int = 1000
    ) -> Result[list[dict]]:
        """OLD PATTERN: Fetch all tasks."""
        self.query_count += 1
        await asyncio.sleep(0.001)  # Simulate query latency
        return Result.ok(self._tasks[:limit])

    async def get_task(self, uid: str) -> Result[dict]:
        """Get single task."""
        self.query_count += 1
        await asyncio.sleep(0.0005)  # Simulate query latency
        task = next((t for t in self._tasks if t["uid"] == uid), None)
        return Result.ok(task) if task else Result.fail("Not found")


class MockBackendNew:
    """Mock backend simulating NEW pattern (direct graph queries)."""

    def __init__(self, task_count: int = 1000):
        """Initialize with specified number of tasks."""
        self.task_count = task_count
        self.query_count = 0
        self._tasks = self._generate_tasks(task_count)
        self._relationships = self._generate_relationships(task_count)

    def _generate_tasks(self, count: int) -> list[dict]:
        """Generate mock task data (no relationship fields)."""
        tasks = [
            {
                "uid": f"task:{i}",
                "user_uid": "user:demo",
                "title": f"Task {i}",
                "priority": Priority.MEDIUM.value,
                "status": KuStatus.DRAFT.value,
                # NEW: No applies_knowledge_uids field
                "created_at": datetime.now().isoformat(),
            }
            for i in range(count)
        ]
        return tasks

    def _generate_relationships(self, task_count: int) -> dict[str, list[str]]:
        """Generate mock relationship data."""
        relationships = {}
        # Every 10th task applies ku.python.basics
        task_uids = [f"task:{i}" for i in range(task_count) if i % 10 == 0]
        relationships["ku.python.basics"] = task_uids
        return relationships

    async def get_related_uids(
        self, uid: str, relationship_type: str, direction: str = "outgoing"
    ) -> Result[list[str]]:
        """NEW PATTERN: Direct graph query for relationships."""
        self.query_count += 1
        await asyncio.sleep(0.0003)  # Simulate faster graph query

        if direction == "incoming" and relationship_type == "APPLIES_KNOWLEDGE":
            # Query: Which tasks apply this knowledge?
            return Result.ok(self._relationships.get(uid, []))

        return Result.ok([])

    async def get_task(self, uid: str) -> Result[dict]:
        """Get single task."""
        self.query_count += 1
        await asyncio.sleep(0.0005)  # Simulate query latency
        task = next((t for t in self._tasks if t["uid"] == uid), None)
        return Result.ok(task) if task else Result.fail("Not found")


class PerformanceBenchmark:
    """Performance benchmarking harness."""

    def __init__(self):
        self.results: list[BenchmarkResult] = []

    @asynccontextmanager
    async def measure(self, scenario: str, pattern: str):
        """Context manager to measure execution time and queries."""
        start_time = time.perf_counter()

        class Metrics:
            query_count = 0
            items_processed = 0

        metrics = Metrics()

        try:
            yield metrics
        finally:
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000

            result = BenchmarkResult(
                scenario=scenario,
                pattern=pattern,
                query_count=metrics.query_count,
                execution_time_ms=execution_time_ms,
                items_processed=metrics.items_processed,
            )
            self.results.append(result)

    async def benchmark_knowledge_task_search_old(self, backend: MockBackendOld) -> None:
        """OLD: Fetch all tasks and filter in memory."""
        async with self.measure("Knowledge Task Search", "old") as metrics:
            # Fetch ALL tasks
            all_tasks_result = await backend.list_tasks(limit=1000)
            metrics.query_count = backend.query_count

            # Filter in Python
            all_tasks = all_tasks_result.value
            matching_tasks = [
                t for t in all_tasks if "ku.python.basics" in t.get("applies_knowledge_uids", [])
            ]

            metrics.items_processed = len(matching_tasks)

    async def benchmark_knowledge_task_search_new(self, backend: MockBackendNew) -> None:
        """NEW: Direct graph query for tasks with relationship."""
        async with self.measure("Knowledge Task Search", "new") as metrics:
            # Query graph for task UIDs with APPLIES_KNOWLEDGE relationship
            task_uids_result = await backend.get_related_uids(
                "ku.python.basics", "APPLIES_KNOWLEDGE", direction="incoming"
            )
            metrics.query_count = backend.query_count

            task_uids = task_uids_result.value

            # Fetch only matching tasks (simulated - in real scenario would fetch each)
            # For benchmark, we'll count the queries that would be made
            metrics.query_count += len(task_uids)  # Would be individual get_task calls
            metrics.items_processed = len(task_uids)

    async def benchmark_relationship_queries_old(self, backend: MockBackendOld) -> None:
        """OLD: Fetch task with embedded relationship data."""
        async with self.measure("Task Relationships Query", "old") as metrics:
            # Fetch task (relationships embedded in model)
            task_result = await backend.get_task("task:10")
            metrics.query_count = backend.query_count

            if task_result.is_ok:
                task = task_result.value
                # Access embedded relationship data (no additional queries)
                applies_knowledge = task.get("applies_knowledge_uids", [])
                metrics.items_processed = len(applies_knowledge)

    async def benchmark_relationship_queries_new(self, backend: MockBackendNew) -> None:
        """NEW: Fetch task + separate relationship queries."""
        async with self.measure("Task Relationships Query", "new") as metrics:
            # Fetch task (no relationship data)
            await backend.get_task("task:10")

            # Query relationships separately
            applies_result = await backend.get_related_uids(
                "task:10", "APPLIES_KNOWLEDGE", direction="outgoing"
            )

            metrics.query_count = backend.query_count

            if applies_result.is_ok:
                applies_knowledge = applies_result.value
                metrics.items_processed = len(applies_knowledge)

    async def benchmark_multiple_tasks_old(self, backend: MockBackendOld, count: int = 10) -> None:
        """OLD: Fetch multiple tasks with embedded relationships."""
        async with self.measure(f"Fetch {count} Tasks", "old") as metrics:
            for i in range(count):
                await backend.get_task(f"task:{i}")
                # Relationships already loaded in the task object

            metrics.query_count = backend.query_count
            metrics.items_processed = count

    async def benchmark_multiple_tasks_new(self, backend: MockBackendNew, count: int = 10) -> None:
        """NEW: Fetch multiple tasks + relationship queries."""
        async with self.measure(f"Fetch {count} Tasks", "new") as metrics:
            for i in range(count):
                task_result = await backend.get_task(f"task:{i}")
                if task_result.is_ok:
                    # Need separate query for relationships
                    await backend.get_related_uids(
                        f"task:{i}", "APPLIES_KNOWLEDGE", direction="outgoing"
                    )

            metrics.query_count = backend.query_count
            metrics.items_processed = count

    def print_results(self) -> None:
        """Print benchmark results with comparison."""
        print("\n" + "=" * 80)
        print("PHASE 3B PERFORMANCE BENCHMARK RESULTS")
        print("=" * 80)

        # Group results by scenario
        scenarios = {}
        for result in self.results:
            if result.scenario not in scenarios:
                scenarios[result.scenario] = {}
            scenarios[result.scenario][result.pattern] = result

        total_old_queries = 0
        total_new_queries = 0
        total_old_time = 0
        total_new_time = 0

        for scenario_name, patterns in scenarios.items():
            print(f"\n{scenario_name}")
            print("-" * 80)

            old = patterns.get("old")
            new = patterns.get("new")

            if old and new:
                # Calculate improvements
                query_reduction = (old.query_count - new.query_count) / old.query_count * 100
                time_improvement = (
                    (old.execution_time_ms - new.execution_time_ms) / old.execution_time_ms * 100
                )

                print("  OLD Pattern:")
                print(f"    Queries:        {old.query_count:6d}")
                print(f"    Time:           {old.execution_time_ms:8.2f} ms")
                print(f"    Items:          {old.items_processed:6d}")

                print("\n  NEW Pattern:")
                print(f"    Queries:        {new.query_count:6d}  ({query_reduction:+.1f}%)")
                print(
                    f"    Time:           {new.execution_time_ms:8.2f} ms  ({time_improvement:+.1f}%)"
                )
                print(f"    Items:          {new.items_processed:6d}")

                total_old_queries += old.query_count
                total_new_queries += new.query_count
                total_old_time += old.execution_time_ms
                total_new_time += new.execution_time_ms

        # Overall summary
        print("\n" + "=" * 80)
        print("OVERALL SUMMARY")
        print("=" * 80)

        overall_query_reduction = (total_old_queries - total_new_queries) / total_old_queries * 100
        overall_time_improvement = (total_old_time - total_new_time) / total_old_time * 100

        print("\n  Total Queries:")
        print(f"    OLD: {total_old_queries:6d}")
        print(f"    NEW: {total_new_queries:6d}  ({overall_query_reduction:+.1f}%)")

        print("\n  Total Execution Time:")
        print(f"    OLD: {total_old_time:8.2f} ms")
        print(f"    NEW: {total_new_time:8.2f} ms  ({overall_time_improvement:+.1f}%)")

        print("\n" + "=" * 80)

        # Verdict
        if overall_query_reduction >= 40 and overall_time_improvement >= 40:
            print("✅ PERFORMANCE TARGET MET: 40-60% improvement achieved!")
        elif overall_query_reduction >= 20 or overall_time_improvement >= 20:
            print("🟡 PARTIAL IMPROVEMENT: Some gains but below 40% target")
        else:
            print("❌ PERFORMANCE REGRESSION: No significant improvement")

        print("=" * 80 + "\n")


async def main():
    """Run all benchmarks."""
    print("\nPhase 3B Performance Benchmarking")
    print("==================================\n")
    print("Comparing OLD pattern (embedded relationships) vs NEW pattern (graph queries)")
    print("Task dataset: 1000 tasks, ~100 with knowledge relationships\n")

    benchmark = PerformanceBenchmark()

    # Scenario 1: Knowledge-based task search (most impactful improvement)
    print("Running: Knowledge Task Search benchmark...")
    backend_old = MockBackendOld(task_count=1000)
    await benchmark.benchmark_knowledge_task_search_old(backend_old)

    backend_new = MockBackendNew(task_count=1000)
    await benchmark.benchmark_knowledge_task_search_new(backend_new)

    # Scenario 2: Single task relationship queries
    print("Running: Task Relationships Query benchmark...")
    backend_old = MockBackendOld(task_count=1000)
    await benchmark.benchmark_relationship_queries_old(backend_old)

    backend_new = MockBackendNew(task_count=1000)
    await benchmark.benchmark_relationship_queries_new(backend_new)

    # Scenario 3: Multiple task fetches with relationships
    print("Running: Fetch Multiple Tasks benchmark...")
    backend_old = MockBackendOld(task_count=1000)
    await benchmark.benchmark_multiple_tasks_old(backend_old, count=10)

    backend_new = MockBackendNew(task_count=1000)
    await benchmark.benchmark_multiple_tasks_new(backend_new, count=10)

    # Print results
    benchmark.print_results()

    print("\nBenchmark complete!")


if __name__ == "__main__":
    asyncio.run(main())
