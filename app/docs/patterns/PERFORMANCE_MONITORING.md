---
title: Performance Monitoring System
updated: 2026-01-31
status: deprecated - see MetricsCache
category: patterns
tags: [monitoring, patterns, performance, deprecated]
related: [PROMETHEUS_METRICS.md, ADR-036]
---

# Performance Monitoring System

**Status:** ⚠️ DEPRECATED (Removed January 31, 2026)
**Replaced By:** MetricsCache + Prometheus
**See:** `/docs/observability/PROMETHEUS_METRICS.md`, `/docs/decisions/ADR-036-prometheus-primary-cache-pattern.md`

## Migration Notice

The `PerformanceMonitor` class has been **removed** and replaced with a Prometheus-first architecture.

### What Changed

| Old System | New System | Purpose |
|------------|-----------|----------|
| `PerformanceMonitor` | `MetricsCache` | In-memory cache (last 100 items) |
| In-memory only | Prometheus | Source of truth (production monitoring) |
| No export | Direct writes | Real-time metrics |

### How to Migrate

**Old Code:**
```python
from core.infrastructure.monitoring import get_performance_monitor

monitor = get_performance_monitor()
await monitor.record_handler_execution(...)
```

**New Code:**
```python
from core.infrastructure.monitoring import MetricsCache, PrometheusMetrics

prometheus_metrics = PrometheusMetrics()
metrics_cache = MetricsCache(prometheus_metrics, enabled=True)

# Metrics written to both Prometheus (always) and cache (if enabled)
await metrics_cache.record_handler_execution(...)
```

### Why the Change?

**Problems with PerformanceMonitor:**
1. **Duplication** - Metrics tracked in both PerformanceMonitor and Prometheus (40%)
2. **Export Lag** - 30-second delay via bridge pattern
3. **Complexity** - Bridge code added maintenance overhead
4. **Ambiguity** - Unclear which system was source of truth

**Benefits of MetricsCache:**
1. ✅ **Single Source of Truth** - Prometheus is THE metrics system
2. ✅ **Zero Export Lag** - Real-time writes (no bridge)
3. ✅ **Reduced Duplication** - Cache is lossy (10% vs 40%)
4. ✅ **Simpler Architecture** - No bridge code
5. ✅ **Maintains Debugging** - Cache provides last 100 items

### Architecture

```
Event Bus
    ↓
MetricsCache.record_*()
    ├─► Prometheus (ALWAYS - production monitoring)
    │   ├── Counter: event_handler_calls_total
    │   ├── Histogram: event_handler_duration_seconds
    │   └── Counter: context_invalidations_total
    │
    └─► Cache (optional - debugging only)
        └── Deque (maxlen=100) - Last 100 items per metric
```

### MetricsCache API

**Recording Metrics:**
```python
# Handler execution
await metrics_cache.record_handler_execution(
    event_type="task.completed",
    handler_name="on_task_completed",
    duration_ms=45.0,
    error=None  # or Exception instance
)

# Event publication
await metrics_cache.record_event_publication(
    event_type="task.completed",
    duration_ms=75.0,
    handlers_called=3
)

# Context invalidation
await metrics_cache.record_context_invalidation(
    user_uid="user_123",
    duration_ms=50.0,
    reason="task_completed",
    affected_contexts=["askesis", "search"]
)
```

**Querying Cache (Debugging):**
```python
# Get handler metrics (last 100 calls per handler)
handler_metrics = await metrics_cache.get_handler_metrics()

# Get slow handlers
slow_handlers = await metrics_cache.get_slow_handlers(threshold_ms=100.0)

# Get event metrics
event_metrics = await metrics_cache.get_event_metrics()

# Get context invalidation metrics
context_metrics = await metrics_cache.get_context_invalidation_metrics(user_uid="user_123")

# Get summary
summary = await metrics_cache.get_summary()
```

**Querying Prometheus (Production):**
```promql
# Handler execution rate
rate(skuel_event_handler_calls_total[5m])

# p95 handler duration
histogram_quantile(0.95, skuel_event_handler_duration_seconds)

# Slow handlers
skuel_event_handler_duration_seconds{quantile="0.95"} > 0.1
```

### Tests

**Old:** `tests/test_performance_monitoring.py` (removed)
**New:** `tests/test_metrics_cache.py`

Run tests:
```bash
poetry run pytest tests/test_metrics_cache.py -v
```

### Documentation

- **Architecture:** `/docs/observability/PROMETHEUS_METRICS.md`
- **Decision:** `/docs/decisions/ADR-036-prometheus-primary-cache-pattern.md`
- **Summary:** `/METRICS_REFACTOR_COMPLETE.md`

### Timeline

- **2025-10-16:** PerformanceMonitor created
- **2026-01-30:** MetricsCache created, bridge pattern implemented
- **2026-01-31:** PerformanceMonitor removed, bridge removed, Phase 1 complete

---

**For current metrics documentation, see:**
- `/docs/observability/PROMETHEUS_METRICS.md` - Complete metrics guide
- `/docs/decisions/ADR-036-prometheus-primary-cache-pattern.md` - Architecture decision
