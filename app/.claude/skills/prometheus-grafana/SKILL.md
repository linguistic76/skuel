---
name: prometheus-grafana
description: Expert guide for Prometheus metrics and Grafana dashboards in SKUEL. Use when instrumenting features, writing PromQL queries, creating dashboards, or troubleshooting the observability stack.
allowed-tools: Read, Grep, Glob, Bash
---

# Prometheus + Grafana: SKUEL Observability Stack

> "Prometheus as primary, cache as debugging - real-time operational intelligence"

SKUEL uses Prometheus for metrics collection and Grafana for visualization, following the **Prometheus-primary architecture pattern** (ADR-036).

## Quick Start

### What is This Stack?

**Prometheus**: Time-series database that scrapes metrics from `/metrics` endpoint every 15 seconds
**Grafana**: Visualization platform with 4 production dashboards for operational intelligence
**Architecture**: Direct writes to Prometheus (zero lag), optional in-memory cache for debugging

### The 39 Metrics

SKUEL tracks 39 metrics across 7 categories:

| Category | Metrics | Purpose | Examples |
|----------|---------|---------|----------|
| **HTTP** (3) | Requests, latency, errors | API performance | `skuel_http_requests_total`, `skuel_http_request_duration_seconds` |
| **Database** (3) | Queries, duration, errors | Neo4j performance | `skuel_neo4j_queries_total`, `skuel_neo4j_query_duration_seconds` |
| **Events** (6) | Publications, handlers, invalidations | Event bus health | `skuel_events_published_total`, `skuel_event_handler_duration_seconds` |
| **Domains** (2) | Creation, completion | Business activity | `skuel_entities_created_total`, `skuel_entities_completed_total` |
| **Relationships** (16) | Graph density, layers, dependencies, knowledge-subgraph health | Graph health | `skuel_graph_density`, `skuel_blocking_relationships_count`, `skuel_knowledge_orphan_kus_count` |
| **Queries** (3) | Operations, duration, errors | Granular performance | `skuel_operation_calls_total`, `skuel_operation_duration_seconds` |
| **AI Services** (6) | AI API calls, embeddings | AI cost & performance | `skuel_ai_requests_total`, `skuel_embedding_queue_size` |

### The 4 Grafana Dashboards

| Dashboard | Focus | Key Panels | Use Case |
|-----------|-------|------------|----------|
| **System Health** | HTTP & API | Request rate, latency (p50/p95/p99), error rates | Monitor API performance, debug slow endpoints |
| **Domain Activity** | Business metrics | Entity creation/completion by domain | Track user engagement, feature adoption |
| **Graph Health** | Relationship patterns | Graph density, orphaned entities | Ensure graph integrity, optimize relationships |
| **Event Bus** | Event bus health | Publication rate, handler latency, errors | Detect handler regressions, debug event processing |

### Start the Stack

```bash
# Start Neo4j + App + Prometheus + Grafana (monitoring is an opt-in compose profile)
./dev up-monitoring          # alias for: docker compose --profile monitoring up

# Verify Prometheus is scraping
curl http://localhost:8000/metrics | grep skuel_

# Access Grafana dashboards
open http://localhost:3000
# Default credentials: admin/admin
```

Scrape interval 15s, TSDB retention 7 days, 13 alerting rules (incl. the AuraDB Free cap alerts) — see [ALERTING.md](ALERTING.md).

---

## Architecture Overview

### Prometheus-Primary Pattern (ADR-036)

**Core Principle**: Prometheus is the **source of truth** for all metrics. In-memory cache is optional and lossy.

```
Event/Operation
    |
    +--> PrometheusMetrics (ALWAYS - source of truth)
    |         |
    |         +--> prometheus_client.Counter.inc()
    |         +--> prometheus_client.Histogram.observe()
    |         +--> prometheus_client.Gauge.set()
    |
    +--> MetricsCache (OPTIONAL - debugging only)
              |
              +--> deque.append() (last 100 items, lossy)
```

**Key Design Decisions**:
- **Zero export lag**: Metrics written directly to Prometheus, not buffered
- **Cache is lossy**: Only last 100 items retained for debugging
- **No bridge code**: Removed 30-second export delay from Phase 2
- **Fail-fast philosophy**: Cache is optional, Prometheus is required

**Benefits**:
- ✅ Real-time metrics (no 30s lag)
- ✅ Single source of truth (no inconsistency)
- ✅ Unit tests don't need Prometheus running (use cache)
- ✅ Production monitoring unaffected by cache state

**See**: `/docs/decisions/ADR-036-prometheus-primary-cache-pattern.md`

### Production Posture (PR #803): One Surface

Prometheus text exposition is THE metrics surface. The JSON `/api/monitoring/*` trio and the
admin `/api/metrics` route were deleted in PR #803 — do not reintroduce JSON metrics endpoints.

- **The droplet runs no Prometheus/Grafana.** The monitoring profile exists in
  `docker-compose.production.yml` but is not started; production = app + Caddy only.
- The app binds loopback-only (`127.0.0.1:5001`) and **Caddy returns 403 for public `/metrics`**
  (it is auth-exempt app-side so a local scraper could read it; nothing should scrape it over
  the internet — it leaks internal telemetry).
- On-droplet reads: `docker compose exec skuel-app curl -s localhost:5001/metrics`
- Consequence: alert rules currently evaluate only in the dev stack (see ALERTING.md § Where
  alerts actually evaluate).

### Emit-First Doctrine

No metric definition without live emission **in the same change** — 14 defined-but-never-emitted
metrics were deleted in May 2026 (commit 5b477a281: SystemMetrics, SearchMetrics, token/transcription
counters). Genuinely staged instrumentation belongs in `scripts/detect_bloat.py`'s PLANNED tier,
not in `prometheus_metrics.py`. **See:** [INSTRUMENTATION.md](INSTRUMENTATION.md) § Emit-First Doctrine.

---

## Metric Categories Reference

### 1. HTTP Metrics (3 metrics)

**Class**: `HttpMetrics`

| Metric | Type | Labels | Buckets/Purpose |
|--------|------|--------|-----------------|
| `skuel_http_requests_total` | Counter | `method`, `endpoint`, `status` | Total requests |
| `skuel_http_request_duration_seconds` | Histogram | `method`, `endpoint` | Latency (0.01s to 10s) |
| `skuel_http_errors_total` | Counter | `method`, `endpoint`, `status` | Error count |

**Histogram Buckets**: `(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)` seconds

**Usage**:
```python
# Via HttpMetricsTracker (automatic)
@instrument_handler(metrics, endpoint_name="/api/tasks/create")
async def create_task_handler(request):
    # Metrics tracked automatically
    ...

# Manual tracking
prometheus_metrics.http.requests_total.labels(
    method="POST", endpoint="/api/tasks", status=201
).inc()
```

**See**: [INSTRUMENTATION.md](INSTRUMENTATION.md) for HTTP instrumentation patterns

### 2. Database Metrics (3 metrics)

**Class**: `DatabaseMetrics`

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_neo4j_queries_total` | Counter | `operation`, `label` | Query count by type |
| `skuel_neo4j_query_duration_seconds` | Histogram | `operation`, `label` | Query latency |
| `skuel_neo4j_errors_total` | Counter | `operation` | Query failures |

**Operation Values**: `create`, `read`, `update`, `delete`
**Label Values**: Neo4j node labels (`Task`, `Goal`, `Habit`, `Ku`, etc.)

**Usage**:
```python
# Auto-tracked by UniversalNeo4jBackend
prometheus_metrics.db.queries_total.labels(
    operation="create", label="Task"
).inc()

prometheus_metrics.db.query_duration.labels(
    operation="read", label="Goal"
).observe(0.15)  # 150ms
```

### 3. Event Metrics (6 metrics)

**Class**: `EventMetrics`

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_events_published_total` | Counter | `event_type` | Publication count |
| `skuel_event_publish_duration_seconds` | Histogram | `event_type` | Publication overhead |
| `skuel_event_handler_calls_total` | Counter | `event_type`, `handler` | Handler invocations |
| `skuel_event_handler_duration_seconds` | Histogram | `event_type`, `handler` | Handler execution time |
| `skuel_event_handler_errors_total` | Counter | `event_type`, `handler` | Handler failures |
| `skuel_context_invalidations_total` | Counter | None | UserContext invalidations |

**Histogram Buckets**:
- Publish: `(0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0)` seconds
- Handler: `(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)` seconds

**Usage**:
```python
# Auto-tracked by EventBus and MetricsEventHandler
prometheus_metrics.events.events_published_total.labels(
    event_type="TaskCompleted"
).inc()

prometheus_metrics.events.event_handler_duration_seconds.labels(
    event_type="TaskCompleted", handler="update_knowledge_substance"
).observe(0.08)
```

### 4. Domain Metrics (2 metrics)

**Class**: `DomainMetrics`

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_entities_created_total` | Counter | `entity_type` | Creation tracking |
| `skuel_entities_completed_total` | Counter | `entity_type` | Completion tracking |

**Entity Types**: `task`, `goal`, `habit`, `event`, `choice`, `principle`, `journal`, `transcription`, `ku`, `ps`, `lp`, `user_entry`

**Usage**:
```python
# Auto-tracked by MetricsEventHandler on domain events
prometheus_metrics.domains.entities_created.labels(
    entity_type="task"
).inc()

prometheus_metrics.domains.entities_completed.labels(
    entity_type="goal"
).inc()
```

**See**: `core/infrastructure/monitoring/metrics_event_handler.py` for event subscriptions

### 5. Relationship Metrics (16 metrics — 10 base + 6 knowledge-scoped, ADR-080 H1)

**Class**: `RelationshipMetrics`

Tracks SKUEL's four relationship layers:
1. **Hierarchical** - Parent/child (CONTAINS, ORGANIZES)
2. **Lateral** - Sibling/dependency (BLOCKS, ENABLES, RELATED_TO)
3. **Semantic** - Meaning-based (80+ types with namespaces)
4. **Cross-domain** - Between domains (SERVES_LIFE_PATH)

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_graph_density` | Gauge | None | Avg relationships per entity |
| `skuel_total_entities` | Gauge | None | Total entity count |
| `skuel_total_relationships` | Gauge | None | Total relationship count |
| `skuel_orphaned_entities_count` | Gauge | None | Isolated nodes |
| `skuel_relationships_count` | Gauge | `layer` | Count by layer |
| `skuel_lateral_relationships_by_category` | Gauge | `category` | Lateral breakdown |
| `skuel_blocking_relationships_count` | Gauge | None | Active BLOCKS |
| `skuel_enables_relationships_count` | Gauge | None | Active ENABLES |
| `skuel_contains_relationships_count` | Gauge | None | CONTAINS count |
| `skuel_organizes_relationships_count` | Gauge | None | ORGANIZES count |

**Layer Values**: `hierarchical`, `lateral`, `semantic`, `cross_domain`
**Category Values**: `structural`, `dependency`, `semantic`, `associative`

**Updated By**: `update_graph_health_metrics()` background loop in `scripts/dev/bootstrap.py` (every 5 minutes, 4 Cypher queries)

#### Knowledge-subgraph structural health (6 gauges, ADR-080 Horizon 1)

Added in #770. A **knowledge-scoped** view of graph health — the raw structural signals the
`KnowledgeHealthService` (`core/services/analytics/knowledge_health_service.py`) interprets into a
composite GDS-readiness score. Scoped to the knowledge subgraph (Ku / PathStep / LearningPath /
Exercise) matched by `entity_type`, with learner-state telemetry edges excluded so user activity
never inflates connectivity. Same `RelationshipMetrics` class, same 5-min poller (a 4th query added
to the existing `update_graph_health_metrics()` in `scripts/dev/bootstrap.py` — **no new worker**,
preserving the CORE "no background workers" guarantee).

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_knowledge_kus_total` | Gauge | None | Total Ku nodes in the knowledge subgraph |
| `skuel_knowledge_orphan_kus_count` | Gauge | None | Kus with zero incident relationships (isolated knowledge) |
| `skuel_knowledge_avg_ku_degree` | Gauge | None | Average incident relationships per Ku (connectivity) |
| `skuel_knowledge_composed_kus_count` | Gauge | None | Kus composed into ≥1 PathStep (USES_KU/CONTAINS_KNOWLEDGE/TRAINS_KU) |
| `skuel_knowledge_prerequisite_edges_count` | Gauge | None | Prerequisite-DAG edges among knowledge nodes |
| `skuel_knowledge_organizes_edges_count` | Gauge | None | ORGANIZES/MOC edges among knowledge nodes |

These pair with the admin `/admin/knowledge-health` report and `./dev knowledge-health [--json]`
(the on-demand full report with orphan lists + authoring flags); the gauges are the continuously-polled
subset. They have no Grafana panels yet — adding a Knowledge Health row to the Graph Health dashboard
is an open follow-up. **See:** `/docs/decisions/ADR-080-auradb-three-horizon-strategy.md`, base-analytics-service skill.

### 6. Query Metrics (3 metrics)

**Class**: `QueryMetrics`

More granular than DatabaseMetrics - tracks individual operation performance.

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_operation_calls_total` | Counter | `operation_name` | Operation count |
| `skuel_operation_duration_seconds` | Histogram | `operation_name` | Operation latency |
| `skuel_operation_errors_total` | Counter | `operation_name` | Operation failures |

**Operation Names**: `ku_search_by_title`, `ls_add_knowledge`, `task_complete_with_context`, etc.
**Duration Buckets**: `(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)`

---

### 7. AI Service Metrics (6 metrics)

**Class**: `AiMetrics`

Tracks AI API calls (OpenAI LLM, HuggingFace embeddings). Critical for monitoring expensive AI operations.

#### AI API Metrics (3 metrics)

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_ai_requests_total` | Counter | `operation`, `model` | Total AI API requests |
| `skuel_ai_duration_seconds` | Histogram | `operation`, `model` | AI API call duration |
| `skuel_ai_errors_total` | Counter | `operation`, `error_type` | AI API errors |

**Operations**: `embeddings`, `chat`, `completion`
**Models**: `text-embedding-3-small`, `gpt-4o`, etc.
**Error Types**: `rate_limit`, `timeout`, `auth`, `unknown`
**Duration Buckets**: `(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)`

**Example Queries**:
```promql
# AI request rate by model
sum by (model) (rate(skuel_ai_requests_total[5m]))

# Average AI latency
histogram_quantile(0.50, rate(skuel_ai_duration_seconds_bucket[5m]))

# AI error rate
sum(rate(skuel_ai_errors_total[5m]))
/ sum(rate(skuel_ai_requests_total[5m]))
```

#### Embedding Worker Metrics (3 metrics)

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_embedding_queue_size` | Gauge | `queue_type` | Pending embeddings in queue |
| `skuel_embeddings_processed_total` | Counter | `entity_type`, `status` | Total embeddings processed |
| `skuel_embedding_batch_size` | Histogram | - | Batch size distribution |

**Queue Types**: `entity` (tasks/goals/etc.), `chunk` (KU chunks)
**Entity Types**: `task`, `goal`, `habit`, `event`, `choice`, `principle`
**Statuses**: `success`, `failed`
**Batch Buckets**: `(1, 5, 10, 25, 50, 100)`

**Example Queries**:
```promql
# Embedding queue backlog
skuel_embedding_queue_size{queue_type="entity"}

# Embedding success rate
sum(rate(skuel_embeddings_processed_total{status="success"}[5m]))
/ sum(rate(skuel_embeddings_processed_total[5m]))

# Average batch size
histogram_quantile(0.50, rate(skuel_embedding_batch_size_bucket[5m]))

# Embeddings by entity type
sum by (entity_type) (rate(skuel_embeddings_processed_total[5m]))
```

**Instrumentation Locations** (the vendor SDK calls live below the hexagonal boundary in `adapters/external/`; the metrics are recorded in the consuming core services that hold the injected `prometheus_metrics` — W1 / ADR-063):
- Embedding inference call (text → vector): `adapters/external/embeddings/huggingface_adapter.py` (HuggingFace `feature_extraction`); metrics recorded in `core/services/embeddings_service.py`
- LLM chat-completion calls: `adapters/external/llm/{openai,anthropic}_adapter.py`
- Embedding worker: `core/services/background/embedding_worker.py`
- Prometheus metrics passed to services/backends in `compose_services()` via `prometheus_metrics=` parameter

**Key Alerts** (see `ALERTING.md`):
- `HighAIErrorRate` - >20% API failures
- `EmbeddingQueueBacklog` - >500 pending items
- `HighEmbeddingFailureRate` - >20% failed embeddings
- `SlowAICalls` - p95 >30s

---

## Grafana Dashboards

### 1. System Health Dashboard

**File**: `/monitoring/grafana/dashboards/system_health.json`
**Focus**: HTTP and API performance

**Key Panels**:
1. **HTTP Request Rate (QPS)**: `rate(skuel_http_requests_total[5m])`
2. **HTTP Latency (p50/p95/p99)**: `histogram_quantile(0.95, rate(skuel_http_request_duration_seconds_bucket[5m]))`
3. **HTTP Error Rate**: `100 * sum(rate(skuel_http_requests_total{status=~"5.."}[5m])) / sum(rate(skuel_http_requests_total[5m]))`
4. **Top Slowest Endpoints**: Latency aggregated by endpoint
5. **Request Volume by Endpoint**: `sum by (endpoint) (rate(skuel_http_requests_total[5m]))`

**Use Case**: Debug slow API endpoints, monitor error rates, track QPS

### 2. Domain Activity Dashboard

**File**: `/monitoring/grafana/dashboards/domain_activity.json`
**Focus**: Business-level metrics

**Key Panels**:
1. **Entity Creation Rate**: `rate(skuel_entities_created_total[5m])` by entity_type
2. **Entity Completion Rate**: `rate(skuel_entities_completed_total[5m])` by entity_type
3. **Completion Percentage**: `(completed / created) * 100`
4. **User Engagement Heatmap**: Creation events by hour/day

**Use Case**: Track feature adoption, monitor user engagement, identify trends

### 3. Graph Health Dashboard

**File**: `/monitoring/grafana/dashboards/graph_health.json`
**Focus**: Relationship patterns and graph integrity

**Key Panels**:
1. **Graph Density**: `skuel_graph_density` (higher = more connected)
2. **Orphaned Entities**: `skuel_orphaned_entities_count` (target: 0)
3. **Relationship Breakdown by Layer**: `skuel_relationships_count` stacked by layer
4. **Blocking Dependencies**: `skuel_blocking_relationships_count`

**Use Case**: Ensure graph integrity, optimize relationship structure, detect anomalies

### 4. Event Bus Dashboard

**File**: `/monitoring/grafana/dashboards/event_bus.json`
**Focus**: Event bus health

**Key Panels**:
1. **Event Publication Rate**: `rate(skuel_events_published_total[5m])`
2. **Event Handler Latency**: `skuel_event_handler_duration_seconds` histogram
3. **Event Handler Errors**: `skuel_event_handler_errors_total`

**Use Case**: Debug event processing, optimize handler performance, track invalidations

---

## Common Workflows

### Verify Metrics Are Populating

```bash
# 1. Check /metrics endpoint
curl http://localhost:8000/metrics | grep skuel_http_requests_total

# Expected output:
# skuel_http_requests_total{endpoint="/tasks",method="GET",status="200"} 42.0

# 2. Check Prometheus targets
open http://localhost:9090/targets
# Should show "skuel-app" target as UP

# 3. Query in Prometheus UI
open http://localhost:9090/graph
# Query: skuel_http_requests_total
# Should show time series data
```

### Create a New Dashboard Panel

1. **Open Grafana**: http://localhost:3000
2. **Select dashboard** → Add Panel → Add Visualization
3. **Write PromQL query**:
   ```promql
   rate(skuel_entities_created_total{entity_type="task"}[5m])
   ```
4. **Configure visualization**:
   - Panel type: Time series
   - Legend format: `{{entity_type}}`
   - Unit: `ops` (operations per second)
5. **Save dashboard**

**See**: [PROMQL_PATTERNS.md](PROMQL_PATTERNS.md) for query examples

### Debug Slow Endpoints

```promql
# 1. Find slowest endpoints (p95 latency)
topk(5,
  histogram_quantile(0.95,
    sum by (endpoint, le) (
      rate(skuel_http_request_duration_seconds_bucket[5m])
    )
  )
)

# 2. Check error rate for slow endpoint
sum(rate(skuel_http_requests_total{endpoint="/api/tasks/create",status=~"5.."}[5m]))

# 3. Correlate with database queries
rate(skuel_neo4j_queries_total{label="Task"}[5m])
```

### Monitor Event Processing Health

```promql
# 1. Event handler error rate
sum by (handler) (rate(skuel_event_handler_errors_total[5m]))

# 2. Slow event handlers (>500ms p95)
histogram_quantile(0.95,
  rate(skuel_event_handler_duration_seconds_bucket[5m])
) > 0.5

# 3. Context invalidation spike detection
rate(skuel_context_invalidations_total[5m]) > 10
```

---

## Key Implementation Files

| File | Purpose |
|------|---------|
| `/core/infrastructure/monitoring/prometheus_metrics.py` | **Canonical metric definitions** (39 metrics, 7 metric-group classes) |
| `/core/infrastructure/monitoring/metrics_cache.py` | In-memory cache for debugging (optional, lossy) |
| `/core/infrastructure/monitoring/metrics_event_handler.py` | Domain event subscriptions for entity tracking |
| `/core/infrastructure/monitoring/http_instrumentation.py` | HTTP request instrumentation |
| `/adapters/inbound/metrics_routes.py` | `/metrics` endpoint for Prometheus scraper |
| `/monitoring/prometheus/prometheus.yml` | Prometheus scrape configuration (15s interval; `prometheus.dev.yml` variant for a host-run app) |
| `/monitoring/prometheus/alerts.yml` | 13 alerting rules (ground truth for ALERTING.md) |
| `/monitoring/grafana/dashboards/*.json` | 4 production dashboards |
| `/docker-compose.yml` | Development stack — Prometheus + Grafana behind the `monitoring` profile |

---

## Related Skills

- **[python](../python/SKILL.md)** - Python patterns and protocols
- **[result-pattern](../result-pattern/SKILL.md)** - Result[T] error handling
- **[neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md)** - Graph query patterns
- **[base-analytics-service](../base-analytics-service/SKILL.md)** - Analytics without AI

---

## Deep Dive Resources

**Architecture:**
- [ADR-036](/docs/decisions/ADR-036-prometheus-primary-cache-pattern.md) - Prometheus-primary architecture decision

**Patterns:**
- [PROMETHEUS_METRICS.md](/docs/observability/PROMETHEUS_METRICS.md) - Comprehensive metrics reference

**Troubleshooting:**
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common observability issues

**Configuration:**
- [monitoring/prometheus/prometheus.yml](/monitoring/prometheus/prometheus.yml) - Prometheus configuration
- [monitoring/grafana/dashboards/](/monitoring/grafana/dashboards/) - Grafana dashboard JSON files

---

## See Also

- [PROMQL_PATTERNS.md](PROMQL_PATTERNS.md) - PromQL query examples from dashboards
- [INSTRUMENTATION.md](INSTRUMENTATION.md) - How to add metrics to features
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues and debugging
- `/docs/observability/PROMETHEUS_METRICS.md` - Comprehensive reference
- `/docs/decisions/ADR-036-prometheus-primary-cache-pattern.md` - Architecture rationale
