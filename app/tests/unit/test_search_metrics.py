"""
Unit tests for search metrics models and tracking.

Tests SearchMetrics dataclass and metrics collection.

Created: January 2026
"""

from datetime import datetime

import pytest

from core.models.semantic import SearchMetrics, SearchMetricsAggregate


def test_search_metrics_creation():
    """Test creating a SearchMetrics instance."""
    metrics = SearchMetrics(
        query="python programming",
        search_type="hybrid",
        label="Ku",
        num_results=10,
        avg_similarity=0.82,
        min_similarity=0.71,
        max_similarity=0.94,
        latency_ms=45.2,
        timestamp=datetime(2026, 1, 29, 12, 30, 45),
        vector_weight=0.5,
        min_score_threshold=0.75,
    )

    assert metrics.query == "python programming"
    assert metrics.search_type == "hybrid"
    assert metrics.label == "Ku"
    assert metrics.num_results == 10
    assert metrics.avg_similarity == 0.82
    assert metrics.min_similarity == 0.71
    assert metrics.max_similarity == 0.94
    assert metrics.latency_ms == 45.2
    assert metrics.vector_weight == 0.5
    assert metrics.min_score_threshold == 0.75


def test_search_metrics_to_dict():
    """Test converting metrics to dictionary."""
    metrics = SearchMetrics(
        query="test query",
        search_type="vector",
        label="Task",
        num_results=5,
        avg_similarity=0.85,
        min_similarity=0.75,
        max_similarity=0.95,
        latency_ms=23.456,
        timestamp=datetime(2026, 1, 29, 12, 0, 0),
    )

    result = metrics.to_dict()

    assert result["query"] == "test query"
    assert result["search_type"] == "vector"
    assert result["label"] == "Task"
    assert result["num_results"] == 5
    assert result["avg_similarity"] == 0.85
    assert result["latency_ms"] == 23.46  # Rounded to 2 decimals
    assert "timestamp" in result
    assert isinstance(result["timestamp"], str)  # ISO format


def test_search_metrics_to_log_string():
    """Test formatting metrics for logging."""
    metrics = SearchMetrics(
        query="test query",
        search_type="hybrid",
        label="Ku",
        num_results=8,
        avg_similarity=0.876,
        min_similarity=0.75,
        max_similarity=0.92,
        latency_ms=34.5,
        timestamp=datetime.now(),
    )

    log_str = metrics.to_log_string()

    assert "query='test query'" in log_str
    assert "type=hybrid" in log_str
    assert "label=Ku" in log_str
    assert "results=8" in log_str
    assert "avg_score=0.876" in log_str
    assert "latency=34.5ms" in log_str


def test_search_metrics_long_query_truncated():
    """Test that long queries are truncated in log output."""
    long_query = "a" * 100  # 100 character query

    metrics = SearchMetrics(
        query=long_query,
        search_type="vector",
        label="Ku",
        num_results=10,
        avg_similarity=0.8,
        min_similarity=0.7,
        max_similarity=0.9,
        latency_ms=50.0,
        timestamp=datetime.now(),
    )

    log_str = metrics.to_log_string()

    # Query should be truncated to 50 chars in log string
    assert len(metrics.query) == 100  # Original query unchanged
    assert "a" * 50 in log_str  # Truncated version in log


def test_search_metrics_optional_fields():
    """Test metrics with optional fields set to None."""
    metrics = SearchMetrics(
        query="test",
        search_type="vector",
        label="Task",
        num_results=5,
        avg_similarity=0.8,
        min_similarity=0.7,
        max_similarity=0.9,
        latency_ms=30.0,
        timestamp=datetime.now(),
        # Optional fields omitted
    )

    assert metrics.vector_weight is None
    assert metrics.min_score_threshold is None
    assert metrics.cache_hit is None


def test_search_metrics_aggregate_creation():
    """Test creating a SearchMetricsAggregate instance."""
    aggregate = SearchMetricsAggregate(
        total_queries=100,
        avg_latency_ms=45.5,
        avg_results_per_query=8.2,
        avg_similarity=0.82,
        queries_by_type={"vector": 60, "hybrid": 40},
        queries_by_label={"Ku": 70, "Task": 30},
        p50_latency_ms=40.0,
        p95_latency_ms=85.0,
        p99_latency_ms=120.0,
    )

    assert aggregate.total_queries == 100
    assert aggregate.avg_latency_ms == 45.5
    assert aggregate.avg_results_per_query == 8.2
    assert aggregate.avg_similarity == 0.82
    assert aggregate.queries_by_type == {"vector": 60, "hybrid": 40}
    assert aggregate.queries_by_label == {"Ku": 70, "Task": 30}
    assert aggregate.p50_latency_ms == 40.0
    assert aggregate.p95_latency_ms == 85.0
    assert aggregate.p99_latency_ms == 120.0


def test_search_metrics_aggregate_to_dict():
    """Test converting aggregate metrics to dictionary."""
    aggregate = SearchMetricsAggregate(
        total_queries=50,
        avg_latency_ms=35.678,
        avg_results_per_query=7.5,
        avg_similarity=0.8523,
        queries_by_type={"vector": 30, "hybrid": 20},
        queries_by_label={"Ku": 40, "Task": 10},
        p50_latency_ms=30.0,
        p95_latency_ms=70.0,
        p99_latency_ms=95.0,
    )

    result = aggregate.to_dict()

    assert result["total_queries"] == 50
    assert result["avg_latency_ms"] == 35.68  # Rounded to 2 decimals
    assert result["avg_results_per_query"] == 7.5
    assert result["avg_similarity"] == 0.8523  # 4 decimals
    assert result["queries_by_type"] == {"vector": 30, "hybrid": 20}
    assert result["queries_by_label"] == {"Ku": 40, "Task": 10}


def test_search_metrics_aggregate_summary():
    """Test generating summary string."""
    aggregate = SearchMetricsAggregate(
        total_queries=100,
        avg_latency_ms=45.5,
        avg_results_per_query=8.2,
        avg_similarity=0.82,
        queries_by_type={"vector": 60, "hybrid": 40},
        queries_by_label={"Ku": 70, "Task": 30},
        p50_latency_ms=40.0,
        p95_latency_ms=85.0,
        p99_latency_ms=120.0,
    )

    summary = aggregate.summary()

    assert "Total Queries: 100" in summary
    assert "Avg Latency: 45.5ms" in summary
    assert "p50=40.0" in summary
    assert "p95=85.0" in summary
    assert "p99=120.0" in summary
    assert "Avg Results: 8.2" in summary
    assert "Avg Similarity: 0.820" in summary
    assert "vector" in summary
    assert "hybrid" in summary


def test_search_metrics_frozen():
    """Test that SearchMetrics is immutable (frozen dataclass)."""
    metrics = SearchMetrics(
        query="test",
        search_type="vector",
        label="Ku",
        num_results=5,
        avg_similarity=0.8,
        min_similarity=0.7,
        max_similarity=0.9,
        latency_ms=30.0,
        timestamp=datetime.now(),
    )

    # Should raise FrozenInstanceError when trying to modify
    with pytest.raises(AttributeError):
        metrics.query = "modified"

    with pytest.raises(AttributeError):
        metrics.num_results = 10
