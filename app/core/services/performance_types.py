"""
Performance Optimization Types (Pattern 3C Migration)
======================================================

Frozen dataclasses for performance optimization analysis returns.
Replaces dict[str, Any] with strongly-typed, immutable structures.

Pattern 3C Phase 3: Infrastructure Types (Performance Optimization)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TestConfiguration:
    """Scale test configuration parameters."""

    concurrent_users: int
    requests_per_user: int
    test_duration_seconds: int
    total_requests: int


@dataclass(frozen=True)
class PerformanceResults:
    """Performance test results."""

    requests_completed: int
    requests_failed: int
    avg_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    throughput_rps: float
    cache_hit_rate: float
    error_rate: float


@dataclass(frozen=True)
class ResourceUtilization:
    """Resource utilization metrics."""

    peak_memory_mb: float
    avg_cpu_percent: float
    max_queue_depth: int


@dataclass(frozen=True)
class SLACompliance:
    """SLA compliance metrics."""

    sub_100ms_responses: int
    sub_200ms_responses: int
    target_met: bool


@dataclass(frozen=True)
class ScaleTestResult:
    """Complete scale test result."""

    test_configuration: TestConfiguration
    performance_results: PerformanceResults
    resource_utilization: ResourceUtilization
    sla_compliance: SLACompliance


@dataclass(frozen=True)
class CachePerformance:
    """Current cache performance metrics."""

    hit_rate: float
    total_hits: int
    total_misses: int
    evictions: int
    size_bytes: int


@dataclass(frozen=True)
class CacheOptimization:
    """Cache optimization analysis and recommendations."""

    current_performance: CachePerformance
    optimization_suggestions: list[str]
    recommended_strategy: str  # "adaptive", "lru", "lfu", "current"
    estimated_improvement: float  # 0.0-1.0 percentage improvement


@dataclass(frozen=True)
class AlertThresholds:
    """System alert threshold configuration."""

    min_health_ratio: float  # Minimum health ratio before alert (e.g., 0.8)
    max_unhealthy_components: int  # Maximum unhealthy components before alert
