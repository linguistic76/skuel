# Instrumentation Guide

> How to add Prometheus metrics to new SKUEL features

This guide covers the four instrumentation approaches in SKUEL and when to use each one.

## Decision Tree: Which Metric Type?

```
What are you measuring?
├─ A count that only increases? → Counter
│   Examples: requests, errors, events
│
├─ A value that goes up and down? → Gauge
│   Examples: active entities, queue depth, graph density
│
└─ A distribution of values? → Histogram
    Examples: latency, duration, sizes
```

### Counter vs Gauge vs Histogram

| Type | Purpose | Examples | Query Pattern |
|------|---------|----------|---------------|
| **Counter** | Monotonic increase | `http_requests_total`, `entities_created_total` | Use `rate()` or `increase()` |
| **Gauge** | Current value | `active_entities_count`, `graph_density` | Use directly or with `delta()` |
| **Histogram** | Value distribution | `http_request_duration_seconds`, `search_duration` | Use `histogram_quantile()` for percentiles |

---

## Instrumentation Approach 1: HTTP Metrics (Route Factories)

**Use When**: Adding metrics to API endpoints
**Auto-Tracked**: Yes (via route factory decorators)
**Pattern**: `HttpMetricsTracker` with `@instrument_handler`

### Automatic HTTP Instrumentation

HTTP metrics are automatically tracked by route factories:

```python
from core.infrastructure.monitoring import instrument_handler

# In create_tasks_api_routes()
@rt("/api/tasks/create", methods=["POST"])
@instrument_handler(prometheus_metrics, endpoint_name="/api/tasks/create")
async def create_task_handler(request: Request) -> Result[dict]:
    # Metrics tracked automatically:
    # - skuel_http_requests_total (counter)
    # - skuel_http_request_duration_seconds (histogram)
    # - skuel_http_errors_total (on exception)
    ...
```

**What Gets Tracked**:
- Request count: `skuel_http_requests_total{method="POST", endpoint="/api/tasks/create", status=201}`
- Latency histogram: `skuel_http_request_duration_seconds{method="POST", endpoint="/api/tasks/create"}`
- Errors: `skuel_http_errors_total{method="POST", endpoint="/api/tasks/create", status=500}`

### Manual HTTP Tracking

For routes outside route factories:

```python
from core.infrastructure.monitoring import PrometheusMetrics

async def custom_route_handler(request: Request, prometheus_metrics: PrometheusMetrics):
    start_time = time.time()

    try:
        result = await process_request(request)
        status = 200

        # Track success
        prometheus_metrics.http.requests_total.labels(
            method=request.method,
            endpoint="/custom/route",
            status=status
        ).inc()

        return result

    except Exception as e:
        # Track error
        prometheus_metrics.http.errors_total.labels(
            method=request.method,
            endpoint="/custom/route",
            status=500
        ).inc()
        raise

    finally:
        # Track duration
        duration = time.time() - start_time
        prometheus_metrics.http.request_duration.labels(
            method=request.method,
            endpoint="/custom/route"
        ).observe(duration)
```

---

## Instrumentation Approach 2: Database Metrics (Auto-Tracked)

**Use When**: Working with Neo4j
**Auto-Tracked**: Yes (via `UniversalNeo4jBackend`)
**Pattern**: Metrics tracked in CRUD operations

### How It Works

`UniversalNeo4jBackend` automatically tracks all database operations:

```python
# No manual instrumentation needed!
# UniversalNeo4jBackend tracks:

# CREATE operations
async def create(self, entity: T) -> Result[T]:
    # Auto-tracks: skuel_neo4j_queries_total{operation="create", label="Task"}
    # Auto-tracks: skuel_neo4j_query_duration_seconds{operation="create", label="Task"}
    ...

# READ operations
async def get(self, uid: str) -> Result[T]:
    # Auto-tracks: skuel_neo4j_queries_total{operation="read", label="Task"}
    ...

# UPDATE operations
async def update(self, entity: T) -> Result[T]:
    # Auto-tracks: skuel_neo4j_queries_total{operation="update", label="Task"}
    ...

# DELETE operations
async def delete(self, uid: str) -> Result[bool]:
    # Auto-tracks: skuel_neo4j_queries_total{operation="delete", label="Task"}
    ...
```

### Manual Database Tracking

For custom Cypher queries outside `UniversalNeo4jBackend`:

```python
from core.infrastructure.monitoring import PrometheusMetrics
import time

async def custom_graph_query(
    driver: Any,
    prometheus_metrics: PrometheusMetrics
) -> Result[list[dict]]:
    start_time = time.time()

    try:
        query = """
        MATCH (t:Task)-[:BLOCKS]->(t2:Task)
        RETURN t, t2
        """
        result = await driver.execute_query(query)

        # Track success
        prometheus_metrics.db.queries_total.labels(
            operation="read",
            label="Task"
        ).inc()

        return Result.ok(result)

    except Exception as e:
        # Track error
        prometheus_metrics.db.query_errors.labels(
            operation="read"
        ).inc()
        return Result.fail(Errors.database(str(e)))

    finally:
        # Track duration
        duration = time.time() - start_time
        prometheus_metrics.db.query_duration.labels(
            operation="read",
            label="Task"
        ).observe(duration)
```

---

## Instrumentation Approach 3: Event-Based Metrics

**Use When**: Tracking business events (entity creation, completion, etc.)
**Auto-Tracked**: Yes (via `MetricsEventHandler`)
**Pattern**: Event subscriptions

### How MetricsEventHandler Works

Domain events automatically populate metrics via `MetricsEventHandler`:

```python
# In your service, just publish events as normal
from core.events.task_events import TaskCreated, TaskCompleted

# 1. Service publishes event
await event_bus.publish(TaskCreated(task_uid=uid, user_uid=user_uid))

# 2. MetricsEventHandler auto-increments counter
# skuel_entities_created_total{entity_type="task"} +1
```

**Tracked Events** (January 2026):
- **Creation**: `TaskCreated`, `GoalCreated`, `HabitCreated`, `CalendarEventCreated`, `ChoiceCreated`, `PrincipleCreated`
- **Completion**: `TaskCompleted`, `TasksBulkCompleted`, `HabitCompleted`

### Adding Metrics for New Events

To track a new event type, update `MetricsEventHandler`:

```python
# core/infrastructure/monitoring/metrics_event_handler.py

from core.events.new_domain_events import NewEntityCreated

class MetricsEventHandler:
    def _subscribe_to_creation_events(self) -> None:
        # Add subscription
        self.event_bus.subscribe(NewEntityCreated, self._on_new_entity_created)

    # Add handler
    async def _on_new_entity_created(self, event: NewEntityCreated) -> None:
        """Track new entity creation."""
        self.prometheus_metrics.domains.entities_created.labels(
            entity_type="new_entity"
        ).inc()
```

### Manual Event Metrics

For metrics not tied to domain events:

```python
from core.infrastructure.monitoring import PrometheusMetrics

async def process_background_task(prometheus_metrics: PrometheusMetrics):
    # Track custom event
    prometheus_metrics.events.events_published_total.labels(
        event_type="BackgroundTaskStarted"
    ).inc()

    start_time = time.time()
    try:
        await perform_work()
    finally:
        duration = time.time() - start_time
        prometheus_metrics.events.event_handler_duration_seconds.labels(
            event_type="BackgroundTaskStarted",
            handler="process_background_task"
        ).observe(duration)
```

---

## Instrumentation Approach 4: Background Task Metrics

**Use When**: Tracking periodic graph health checks, cleanup jobs
**Auto-Tracked**: No (manual instrumentation required)
**Pattern**: Periodic Gauge updates

### Graph Health Metrics Pattern

Graph health metrics are updated by background tasks:

```python
# Example: Graph health background task (runs every 5 minutes)

from core.infrastructure.monitoring import PrometheusMetrics

async def update_graph_health_metrics(
    driver: Any,
    prometheus_metrics: PrometheusMetrics,
) -> None:
    """
    Background task to update graph health gauges.

    Runs every 5 minutes via scheduler.
    """
    # Query graph density (system-wide)
    query = """
    MATCH (n)
    OPTIONAL MATCH (n)-[r]-()
    WITH count(DISTINCT n) as entity_count,
         count(r) as rel_count
    RETURN CASE
        WHEN entity_count = 0 THEN 0
        ELSE toFloat(rel_count) / entity_count
    END as density
    """
    result = await driver.execute_query(query)
    density = result[0]["density"]

    # Update gauge (no user_uid — system-wide metric)
    prometheus_metrics.relationships.graph_density.set(density)

    # Query orphaned entities (system-wide)
    orphan_query = """
    MATCH (n)
    WHERE NOT (n)-[]-()
    RETURN count(n) as orphan_count
    """
    orphan_result = await driver.execute_query(orphan_query)
    orphan_count = orphan_result[0]["orphan_count"]

    prometheus_metrics.relationships.orphaned_entities.set(orphan_count)
```

### Scheduling Background Metric Updates

```python
# In bootstrap or scheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# Schedule graph health metrics update every 5 minutes
scheduler.add_job(
    func=update_graph_health_metrics,
    trigger="interval",
    minutes=5,
    args=[driver, prometheus_metrics],
    id="graph_health_metrics",
    replace_existing=True,
)

scheduler.start()
```

---

## Adding a New Metric

### Step 1: Define the Metric

Add to the appropriate class in `prometheus_metrics.py`:

```python
# core/infrastructure/monitoring/prometheus_metrics.py

class DomainMetrics:
    def __init__(self) -> None:
        # Existing metrics...

        # NEW: Track journal entries
        self.journal_entries_created = Counter(
            "skuel_journal_entries_created_total",
            "Total journal entries created",
            ["entry_type"]  # Labels (no user_uid — per-user data belongs in Neo4j)
        )
```

### Step 2: Instrument the Code

Add tracking where the action occurs:

```python
# In JournalsCoreService
from core.infrastructure.monitoring import PrometheusMetrics

class JournalsCoreService:
    def __init__(
        self,
        backend: BackendOperations[Journal],
        prometheus_metrics: PrometheusMetrics | None = None,
    ):
        self.backend = backend
        self.prometheus_metrics = prometheus_metrics

    async def create_journal_entry(
        self,
        request: JournalCreateRequest,
        user_uid: str
    ) -> Result[Journal]:
        result = await self.backend.create(...)

        if result.is_ok and self.prometheus_metrics:
            # Track creation (aggregate — no user_uid)
            self.prometheus_metrics.domains.journal_entries_created.labels(
                entry_type=request.entry_type
            ).inc()

        return result
```

### Step 3: Wire Prometheus Metrics

Ensure `PrometheusMetrics` is passed to your service:

```python
# In services_bootstrap.py

prometheus_metrics = PrometheusMetrics()

journals_service = JournalsService(
    backend=journals_backend,
    prometheus_metrics=prometheus_metrics,  # Pass metrics
)
```

### Step 4: Verify Metrics Populate

```bash
# 1. Trigger the action (create journal entry)
curl -X POST http://localhost:5001/api/journals/create -d '{"entry_type": "reflection"}'

# 2. Check /metrics endpoint
curl http://localhost:5001/metrics | grep skuel_journal_entries_created_total

# Expected output:
# skuel_journal_entries_created_total{entry_type="reflection"} 1.0

# 3. Query in Prometheus
rate(skuel_journal_entries_created_total[5m])
```

### Step 5: Add to Grafana Dashboard

1. Open relevant dashboard (e.g., Domain Activity)
2. Add new panel
3. Use PromQL query:
   ```promql
   sum by (entry_type) (rate(skuel_journal_entries_created_total[5m]))
   ```
4. Configure visualization and save

---

## Testing Instrumentation

### Unit Test Pattern

Use `MetricsCache` for testing (no Prometheus required):

```python
from core.infrastructure.monitoring import PrometheusMetrics, MetricsCache

async def test_journal_creation_increments_metric():
    # Setup
    prometheus_metrics = PrometheusMetrics()
    cache = MetricsCache(prometheus_metrics, enabled=True)

    service = JournalsCoreService(
        backend=mock_backend,
        prometheus_metrics=prometheus_metrics,
    )

    # Act
    await service.create_journal_entry(request, user_uid="user_test")

    # Assert - check cache (not Prometheus)
    # Note: Direct counter value access requires prometheus_client internals
    # Better: Use integration test or check /metrics endpoint
```

### Integration Test Pattern

Test with actual `/metrics` endpoint:

```python
from fasthtml.common import TestClient

async def test_metrics_endpoint_includes_journal_metric():
    # Setup
    app = create_app_with_metrics()
    client = TestClient(app)

    # Trigger action
    response = client.post("/api/journals/create", json={"entry_type": "reflection"})
    assert response.status_code == 201

    # Check metrics endpoint
    metrics_response = client.get("/metrics")
    assert "skuel_journal_entries_created_total" in metrics_response.text
    assert 'entry_type="reflection"' in metrics_response.text
```

---

## Best Practices

### No Per-User Labels

**Prometheus tracks system health, not user behavior.** Never use `user_uid` as a label.

Per-user data belongs in Neo4j (graph relationships, UserContext). Prometheus answers "is the system healthy?" — Neo4j answers "what did user X do?"

```python
# BAD — per-user tracking (cardinality explosion, wrong tool)
prometheus_metrics.domains.entities_created.labels(
    entity_type="task", user_uid=user_uid
).inc()

# GOOD — aggregate system metric
prometheus_metrics.domains.entities_created.labels(
    entity_type="task"
).inc()
```

### Label Cardinality

**Keep label cardinality LOW** - avoid unbounded label values:

```python
# BAD - unbounded cardinality (creates millions of time series)
prometheus_metrics.http.requests_total.labels(
    endpoint=request.path,  # Every unique path = new series
    session_id=session_id,  # Every session = new series
)

# GOOD - bounded cardinality
prometheus_metrics.http.requests_total.labels(
    endpoint="/api/tasks/create",  # Fixed set of endpoints
    method="POST",                 # Only 5-6 HTTP methods
    status=200,                    # Only ~15 status codes
)
```

**Rule of Thumb**: Total time series = (label1_values × label2_values × ... × labelN_values)
- Aim for < 1,000 time series per metric
- Use aggregation in queries instead of pre-creating series

### Naming Conventions

Follow Prometheus naming standards:

```python
# Counters - suffix with _total
skuel_http_requests_total
skuel_entities_created_total

# Gauges - no suffix
skuel_graph_density
skuel_active_entities_count

# Histograms - suffix with unit
skuel_http_request_duration_seconds
skuel_search_duration_seconds

# Use underscores (not camelCase)
skuel_event_handler_calls_total  # GOOD
skuelEventHandlerCallsTotal      # BAD
```

### Histogram Bucket Selection

Choose buckets based on expected value distribution:

```python
# HTTP latency - sub-second to 10s
buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

# Event handler duration - milliseconds to seconds
buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)

# Search similarity scores - 0.0 to 1.0
buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
```

**Rule**: Cover 2-3 orders of magnitude, with higher resolution in the expected range.

### Optional Metrics Pattern

Always check if `prometheus_metrics` is available:

```python
async def some_service_method(self, ...) -> Result[T]:
    result = await self.backend.create(...)

    # Guard against None (metrics are optional)
    if result.is_ok and self.prometheus_metrics:
        self.prometheus_metrics.domains.entities_created.labels(...).inc()

    return result
```

**Why**: Services may run without Prometheus in tests or minimal deployments.

---

## Common Patterns

### Pattern: Measure Duration

```python
import time

start_time = time.time()
try:
    result = await expensive_operation()
finally:
    duration = time.time() - start_time
    prometheus_metrics.queries.operation_duration_seconds.labels(
        operation_name="expensive_operation"
    ).observe(duration)
```

### Pattern: Track Success/Failure

```python
try:
    result = await operation()

    # Track success
    prometheus_metrics.queries.operation_calls_total.labels(
        operation_name="operation"
    ).inc()

except Exception as e:
    # Track failure
    prometheus_metrics.queries.operation_errors_total.labels(
        operation_name="operation"
    ).inc()
    raise
```

### Pattern: Conditional Increment

```python
async def complete_task(self, uid: str) -> Result[Task]:
    result = await self.backend.update_status(uid, "completed")

    if result.is_ok and self.prometheus_metrics:
        self.prometheus_metrics.domains.entities_completed.labels(
            entity_type="task"
        ).inc()

    return result
```

### Pattern: Gauge for Current State

```python
async def recalculate_active_tasks(self):
    active_count = await self.backend.count_active_tasks()

    if self.prometheus_metrics:
        self.prometheus_metrics.domains.active_entities.labels(
            entity_type="task"
        ).set(active_count)
```

---

## See Also

- [SKILL.md](SKILL.md) - Complete observability stack guide
- [PROMQL_PATTERNS.md](PROMQL_PATTERNS.md) - Query examples
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Debugging metrics
- `/core/infrastructure/monitoring/prometheus_metrics.py` - Metric definitions
- `/docs/decisions/ADR-036-prometheus-primary-cache-pattern.md` - Architecture
