"""
Search Metrics Models
====================

Data models for tracking semantic search quality and performance.

Metrics enable:
- Query performance monitoring
- Search quality optimization
- A/B testing different configurations
- Identifying poorly performing queries

Created: January 2026
See: /docs/architecture/SEARCH_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SearchMetrics:
    """
    Metrics for a single search operation.

    Tracks performance, quality, and characteristics of search queries
    to enable optimization and monitoring.

    Attributes:
        query: Original search query text
        search_type: Type of search ("vector", "fulltext", "hybrid")
        label: Entity type searched (e.g., "Ku", "Task", "Goal")
        num_results: Number of results returned
        avg_similarity: Average similarity score (0.0-1.0 for vector, varies for others)
        min_similarity: Minimum similarity score in results
        max_similarity: Maximum similarity score in results
        latency_ms: Query execution time in milliseconds
        timestamp: When the search was executed
        vector_weight: Weight used for vector results (hybrid search only)
        min_score_threshold: Minimum score threshold applied
        cache_hit: Whether embeddings were cached (None if not applicable)

    Example:
        >>> metrics = SearchMetrics(
        ...     query="python programming",
        ...     search_type="hybrid",
        ...     label="Ku",
        ...     num_results=10,
        ...     avg_similarity=0.82,
        ...     min_similarity=0.71,
        ...     max_similarity=0.94,
        ...     latency_ms=45.2,
        ...     timestamp=datetime.now(),
        ... )
    """

    query: str
    search_type: str  # "vector", "fulltext", "hybrid"
    label: str
    num_results: int
    avg_similarity: float
    min_similarity: float
    max_similarity: float
    latency_ms: float
    timestamp: datetime
    vector_weight: float | None = None  # For hybrid search
    min_score_threshold: float | None = None
    cache_hit: bool | None = None

    def to_dict(self) -> dict:
        """
        Convert metrics to dictionary for logging/storage.

        Returns:
            Dictionary representation of metrics
        """
        return {
            "query": self.query,
            "search_type": self.search_type,
            "label": self.label,
            "num_results": self.num_results,
            "avg_similarity": round(self.avg_similarity, 4),
            "min_similarity": round(self.min_similarity, 4),
            "max_similarity": round(self.max_similarity, 4),
            "latency_ms": round(self.latency_ms, 2),
            "timestamp": self.timestamp.isoformat(),
            "vector_weight": self.vector_weight,
            "min_score_threshold": self.min_score_threshold,
            "cache_hit": self.cache_hit,
        }

    def to_log_string(self) -> str:
        """
        Format metrics for log output.

        Returns:
            Human-readable log string
        """
        return (
            f"Search metrics: query='{self.query[:50]}' type={self.search_type} "
            f"label={self.label} results={self.num_results} "
            f"avg_score={self.avg_similarity:.3f} latency={self.latency_ms:.1f}ms"
        )


@dataclass
class SearchMetricsAggregate:
    """
    Aggregated search metrics over multiple queries.

    Used for analyzing search quality trends and performance.

    Attributes:
        total_queries: Total number of queries analyzed
        avg_latency_ms: Average query latency
        avg_results_per_query: Average number of results returned
        avg_similarity: Average similarity score across all queries
        queries_by_type: Count of queries by search type
        queries_by_label: Count of queries by entity label
        p50_latency_ms: Median query latency
        p95_latency_ms: 95th percentile query latency
        p99_latency_ms: 99th percentile query latency
    """

    total_queries: int
    avg_latency_ms: float
    avg_results_per_query: float
    avg_similarity: float
    queries_by_type: dict[str, int]
    queries_by_label: dict[str, int]
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float

    def to_dict(self) -> dict:
        """
        Convert aggregate metrics to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "total_queries": self.total_queries,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "avg_results_per_query": round(self.avg_results_per_query, 2),
            "avg_similarity": round(self.avg_similarity, 4),
            "queries_by_type": self.queries_by_type,
            "queries_by_label": self.queries_by_label,
            "p50_latency_ms": round(self.p50_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "p99_latency_ms": round(self.p99_latency_ms, 2),
        }

    def summary(self) -> str:
        """
        Generate human-readable summary.

        Returns:
            Multi-line summary string
        """
        return f"""
Search Metrics Summary
======================
Total Queries: {self.total_queries}
Avg Latency: {self.avg_latency_ms:.1f}ms (p50={self.p50_latency_ms:.1f}, p95={self.p95_latency_ms:.1f}, p99={self.p99_latency_ms:.1f})
Avg Results: {self.avg_results_per_query:.1f}
Avg Similarity: {self.avg_similarity:.3f}

By Type: {self.queries_by_type}
By Label: {self.queries_by_label}
        """.strip()
