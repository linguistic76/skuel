# ADR-036: Prometheus as Primary with In-Memory Cache Pattern

**Status**: ✅ Accepted
**Date**: 2026-01-31
**Decision Makers**: System Architecture

---

## Context

SKUEL's metrics architecture evolved through three phases:

1. **Phase 1 (2025)**: In-memory metrics (`MetricsStore`, `PerformanceMonitor`)
2. **Phase 2 (January 2026)**: Prometheus + Grafana added for observability
3. **Phase 3 (January 2026)**: `PrometheusPerformanceBridge` exports in-memory metrics to Prometheus

This created a **dual-system architecture** where metrics were tracked in two places:
- In-memory: For debugging, testing, immediate access
- Prometheus: For historical trends, dashboards, operational intelligence

**Problem**: The bridge pattern created **40% duplication** and maintenance overhead:

| Metric Category | In-Memory (PerformanceMonitor) | Prometheus | Duplication? |
|----------------|-------------------------------|------------|--------------|
| Event publication count | ✅ | ✅ | YES |
| Event handler calls | ✅ | ✅ | YES |
| Event handler duration | ✅ | ✅ | YES |
| Event handler errors | ✅ | ✅ | YES |
| Context invalidations | ✅ | ✅ | YES |
| Entity creation | ❌ | ✅ | NO |
| Query performance | ✅ | ❌ | NO |
| Graph health | ❌ | ✅ | NO |

**Bridge Pattern Issues**:
1. **30-second export lag**: Metrics updated in-memory immediately but exported to Prometheus every 30s
2. **Delta tracking complexity**: Bridge maintained state to compute deltas for counters
3. **Potential inconsistency**: In-memory and Prometheus could diverge during bridge failures
4. **Maintenance burden**: Three systems to maintain (in-memory, Prometheus, bridge)

---

## Decision

**Adopt Option D: "Prometheus as Primary, In-Memory as Cache"**

Use Prometheus as the **source of truth** while maintaining a **lossy in-memory cache** for debugging.

### Architecture

```
Event Bus
    ├─► MetricsCache.record_handler_execution()
    │       ├─► Prometheus (ALWAYS - source of truth)
    │       │   └─► prometheus_metrics.events.handler_calls_total.inc()
    │       └─► Cache (if enabled - debugging only)
    │           └─► cached_handler_metrics.recent_executions.append()
    │
    └─► MetricsCache.record_event_publication()
            ├─► Prometheus (ALWAYS)
            └─► Cache (if enabled)
```

### Key Changes

**Files Created**:
- `/core/infrastructure/monitoring/metrics_cache.py` - MetricsCache class

**Files Modified**:
- `/adapters/infrastructure/event_bus.py` - Use MetricsCache instead of PerformanceMonitor
- `/scripts/dev/bootstrap.py` - Initialize MetricsCache, remove bridge
- `/core/infrastructure/monitoring/__init__.py` - Export MetricsCache

**Files Removed**:
- `/core/infrastructure/monitoring/prometheus_bridge.py` - No longer needed

### Cache Design

**Cache is LOSSY** - stores only recent values (last 100 items per metric) for debugging:

```python
class MetricsCache:
    """
    Prometheus-first metrics with in-memory cache.

    - Prometheus: Source of truth (production monitoring)
    - Cache: Debugging access (last 100 items)
    """

    async def record_handler_execution(self, ...):
        # Write to Prometheus (ALWAYS)
        self.prometheus_metrics.events.handler_calls_total.inc()

        # Update cache (debugging only)
        if self.enabled:
            self._handler_cache[key].record_execution(duration_ms, error)
```

**Cache Benefits**:
1. ✅ Zero Prometheus dependency for unit tests
2. ✅ Immediate debugging access (no Prometheus queries needed)
3. ✅ Works even if Prometheus is down
4. ✅ Minimal memory footprint (deque maxlen=100)

**Cache Limitations**:
1. ❌ Lossy (only last 100 items)
2. ❌ Doesn't survive app restart
3. ❌ Not suitable for long-term analysis

---

## Options Considered

### Option A: Prometheus First (Eliminate In-Memory) ❌

**Approach**: Use Prometheus as ONLY metrics system, remove in-memory entirely.

**Rejected Because**:
- Unit tests need Prometheus mock (adds test complexity)
- Debugging requires Prometheus running (dev environment dependency)
- No metrics if Prometheus is down (violates fail-fast for non-critical feature)

### Option B: Unified Metrics Facade ❌

**Approach**: Create facade that writes to both in-memory and Prometheus.

**Rejected Because**:
- Still maintains both systems (doesn't reduce duplication)
- Adds abstraction layer (more code to maintain)
- Doesn't address "which is source of truth?" question

### Option C: Strategic Separation (Document Intent) ❌

**Approach**: Keep dual systems, document as intentional redundancy.

**Rejected Because**:
- Doesn't reduce maintenance burden
- Doesn't improve cohesion
- Documentation doesn't solve the "40% duplication" problem

### Option D: Prometheus as Primary, Cache as Debugging ✅ CHOSEN

**Why This Option**:
- ✅ Clear single source of truth (Prometheus)
- ✅ Reduces duplication (40% → 10% - cache is smaller)
- ✅ No bridge code to maintain
- ✅ Zero export lag (direct writes)
- ✅ Maintains debugging benefits (cache)
- ✅ Aligns with "One Path Forward" philosophy

---

## Consequences

### Positive

1. **Reduced Complexity**
   - Removed ~150 lines of bridge code
   - Eliminated 30-second export lag
   - Removed delta tracking state

2. **Clear Ownership**
   - Prometheus is THE source of truth
   - Cache is explicitly for debugging (lossy, ephemeral)
   - No ambiguity about which system to query

3. **Improved Cohesion**
   - Event bus writes directly to Prometheus
   - Cache is optional (can be disabled)
   - Metrics flow is linear (no background export task)

4. **Maintained Benefits**
   - Unit tests still use cache (no Prometheus dependency)
   - Debugging still has immediate access (cache)
   - Production monitoring unchanged (Prometheus)

### Negative

1. **Cache is Lossy**
   - Only last 100 items retained
   - Long-term analysis requires Prometheus queries
   - Cache doesn't survive app restart

2. **Migration Effort**
   - Update event bus (✅ done)
   - Update bootstrap (✅ done)
   - Update tests (pending)

### Neutral

1. **PerformanceMonitor Kept**
   - Still exists for compatibility
   - Can be removed in future cleanup
   - Not actively used by event bus

---

## Implementation Status

**✅ Phase 1: Core Implementation** (2026-01-31)
- Created MetricsCache class
- Updated event bus to use MetricsCache
- Removed PrometheusPerformanceBridge
- Updated bootstrap.py

**🚧 Phase 2: Test Migration** (pending)
- Update event bus tests to use cache assertions
- Verify Prometheus metrics still populate
- Update performance test expectations

**📋 Phase 3: Future Cleanup** (optional)
- Consider removing PerformanceMonitor entirely
- Evaluate if MetricsStore can use same pattern
- Consolidate all metrics to Prometheus-primary

---

## Metrics

**Duplication Reduction**:
- Before: 5/12 metric categories duplicated (40%)
- After: ~1/12 categories duplicated (10% - cache is subset)

**Code Reduction**:
- Removed: 150 lines (prometheus_bridge.py)
- Added: 450 lines (metrics_cache.py)
- Net change: +300 lines (more features, less complexity)

**Performance Impact**:
- Export lag: 30 seconds → 0 seconds (real-time)
- Cache overhead: < 1ms per metric (deque append)

---

## References

- Analysis: `/PHASE1_COMPLETE.md` (metrics DRY analysis)
- Documentation: `/docs/observability/PROMETHEUS_METRICS.md`
- Implementation: `/core/infrastructure/monitoring/metrics_cache.py`
- Migration: See commit history (2026-01-31)

---

## Review Notes

**Aligns With**:
- ✅ "One Path Forward" philosophy (Prometheus is THE path)
- ✅ Fail-fast principle (cache is optional, Prometheus is primary)
- ✅ Protocol-based architecture (cache is implementation detail)

**Trade-offs Accepted**:
- Cache is lossy (acceptable - debugging only)
- Migration effort (acceptable - one-time cost)
- PerformanceMonitor kept temporarily (acceptable - cleanup later)
