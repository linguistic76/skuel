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

### The 43 Metrics (Phase 1 - January 2026)

SKUEL tracks 43 metrics across 9 categories:

| Category | Metrics | Purpose | Examples |
|----------|---------|---------|----------|
| **System** (3) | CPU, memory, Neo4j health | Infrastructure monitoring | `skuel_cpu_usage_percent`, `skuel_neo4j_connected` |
| **HTTP** (3) | Requests, latency, errors | API performance | `skuel_http_requests_total`, `skuel_http_request_duration_seconds` |
| **Database** (3) | Queries, duration, errors | Neo4j performance | `skuel_neo4j_queries_total`, `skuel_neo4j_query_duration_seconds` |
| **Events** (6) | Publications, handlers, invalidations | Event bus health | `skuel_events_published_total`, `skuel_event_handler_duration_seconds` |
| **Domains** (3) | Creation, completion, active count | Business activity | `skuel_entities_created_total`, `skuel_entities_completed_total` |
| **Relationships** (15) | Graph density, layers, dependencies | Graph health | `skuel_graph_density`, `skuel_blocking_relationships_count` |
| **Search** (3) | Searches, duration, similarity | Search performance | `skuel_searches_total`, `skuel_search_similarity_score` |
| **Queries** (3) | Operations, duration, errors | Granular performance | `skuel_operation_calls_total`, `skuel_operation_duration_seconds` |
| **AI Services** (8) | OpenAI calls, embeddings, transcription | AI cost & performance | `skuel_openai_requests_total`, `skuel_embedding_queue_size` |

### The 4 Grafana Dashboards

| Dashboard | Focus | Key Panels | Use Case |
|-----------|-------|------------|----------|
| **System Health** | HTTP & API | Request rate, latency (p50/p95/p99), error rates | Monitor API performance, debug slow endpoints |
| **Domain Activity** | Business metrics | Entity creation/completion by domain | Track user engagement, feature adoption |
| **Graph Health** | Relationship patterns | Graph density, orphaned entities, dependency chains | Ensure graph integrity, optimize relationships |
| **User Journey** | Event flow | Event handlers, context invalidations | Debug event processing, track user actions |

### Start the Stack

```bash
# Start Prometheus + Grafana (from project root)
docker-compose up -d prometheus grafana

# Verify Prometheus is scraping
curl http://localhost:5001/metrics | grep skuel_

# Access Grafana dashboards
open http://localhost:3000
# Default credentials: admin/admin
```

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

---

## Metric Categories Reference

### 1. System Metrics (3 metrics)

**Class**: `SystemMetrics` in `prometheus_metrics.py`

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_cpu_usage_percent` | Gauge | `user_uid` | CPU usage per user |
| `skuel_memory_usage_bytes` | Gauge | `user_uid` | Memory consumption |
| `skuel_neo4j_connected` | Gauge | None | Neo4j health (1=up, 0=down) |

**Usage**:
```python
prometheus_metrics.system.cpu_usage.labels(user_uid="user_mike").set(45.2)
prometheus_metrics.system.neo4j_connected.set(1)  # Up
```

### 2. HTTP Metrics (3 metrics)

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

### 3. Database Metrics (3 metrics)

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

### 4. Event Metrics (6 metrics)

**Class**: `EventMetrics`

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_events_published_total` | Counter | `event_type` | Publication count |
| `skuel_event_publish_duration_seconds` | Histogram | `event_type` | Publication overhead |
| `skuel_event_handler_calls_total` | Counter | `event_type`, `handler` | Handler invocations |
| `skuel_event_handler_duration_seconds` | Histogram | `event_type`, `handler` | Handler execution time |
| `skuel_event_handler_errors_total` | Counter | `event_type`, `handler` | Handler failures |
| `skuel_context_invalidations_total` | Counter | `user_uid` | UserContext invalidations |

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

### 5. Domain Metrics (3 metrics)

**Class**: `DomainMetrics`

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_entities_created_total` | Counter | `entity_type`, `user_uid` | Creation tracking |
| `skuel_entities_completed_total` | Counter | `entity_type`, `user_uid` | Completion tracking |
| `skuel_active_entities_count` | Gauge | `entity_type`, `user_uid` | Active count |

**Entity Types**: `task`, `goal`, `habit`, `event`, `choice`, `principle`

**Usage**:
```python
# Auto-tracked by MetricsEventHandler on domain events
prometheus_metrics.domains.entities_created.labels(
    entity_type="task", user_uid="user_mike"
).inc()

prometheus_metrics.domains.entities_completed.labels(
    entity_type="goal", user_uid="user_mike"
).inc()
```

**See**: `core/infrastructure/monitoring/metrics_event_handler.py` for event subscriptions

### 6. Relationship Metrics (15 metrics)

**Class**: `RelationshipMetrics`

Tracks SKUEL's four relationship layers:
1. **Hierarchical** - Parent/child (CONTAINS, ORGANIZES)
2. **Lateral** - Sibling/dependency (BLOCKS, ENABLES, RELATED_TO)
3. **Semantic** - Meaning-based (80+ types with namespaces)
4. **Cross-domain** - Between domains (SERVES_LIFE_PATH)

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_graph_density` | Gauge | `user_uid` | Avg relationships per entity |
| `skuel_total_entities` | Gauge | `user_uid` | Total entity count |
| `skuel_total_relationships` | Gauge | `user_uid` | Total relationship count |
| `skuel_orphaned_entities_count` | Gauge | `user_uid` | Isolated nodes |
| `skuel_relationships_count` | Gauge | `layer`, `user_uid` | Count by layer |
| `skuel_lateral_relationships_by_category` | Gauge | `category`, `user_uid` | Lateral breakdown |
| `skuel_blocking_relationships_count` | Gauge | `user_uid` | Active BLOCKS |
| `skuel_enables_relationships_count` | Gauge | `user_uid` | Active ENABLES |
| `skuel_dependency_chain_max_length` | Gauge | `user_uid` | Longest chain |
| `skuel_contains_relationships_count` | Gauge | `user_uid` | CONTAINS count |
| `skuel_organizes_relationships_count` | Gauge | `user_uid` | ORGANIZES count |
| `skuel_semantic_relationships_count` | Gauge | `tier`, `user_uid` | Semantic by tier |
| `skuel_cross_domain_relationships_count` | Gauge | `from_domain`, `to_domain`, `user_uid` | Cross-domain |
| `skuel_graph_traversal_avg_depth` | Gauge | `user_uid` | Avg query depth |

**Layer Values**: `hierarchical`, `lateral`, `semantic`, `cross_domain`
**Category Values**: `structural`, `dependency`, `semantic`, `associative`

**Updated By**: Background task (every 5 minutes) running Neo4j queries

### 7. Search Metrics (3 metrics)

**Class**: `SearchMetrics`

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_searches_total` | Counter | `search_type` | Search count |
| `skuel_search_duration_seconds` | Histogram | `search_type` | Search latency |
| `skuel_search_similarity_score` | Histogram | `search_type` | Result relevance |

**Search Types**: `vector`, `fulltext`, `hybrid`
**Similarity Buckets**: `(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)`

### 8. Query Metrics (3 metrics)

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

### 9. AI Service Metrics (8 metrics) - Phase 1 (January 2026)

**Class**: `AiMetrics`

Tracks OpenAI API calls, embedding generation, and Deepgram transcription. Critical for monitoring expensive AI operations and enabling cost optimization.

#### OpenAI API Metrics (4 metrics)

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_openai_requests_total` | Counter | `operation`, `model` | Total OpenAI API requests |
| `skuel_openai_duration_seconds` | Histogram | `operation`, `model` | OpenAI API call duration |
| `skuel_openai_tokens_total` | Counter | `operation`, `model`, `token_type` | Token consumption |
| `skuel_openai_errors_total` | Counter | `operation`, `error_type` | OpenAI API errors |

**Operations**: `embeddings`, `chat`, `completion`
**Models**: `text-embedding-3-small`, `gpt-4`, etc.
**Token Types**: `prompt`, `completion`
**Error Types**: `rate_limit`, `timeout`, `auth`, `unknown`
**Duration Buckets**: `(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)`

**Example Queries**:
```promql
# OpenAI request rate by model
sum by (model) (rate(skuel_openai_requests_total[5m]))

# Average OpenAI latency
histogram_quantile(0.50, rate(skuel_openai_duration_seconds_bucket[5m]))

# Token usage by operation (cost tracking)
sum by (operation) (rate(skuel_openai_tokens_total[1h]))

# OpenAI error rate
sum(rate(skuel_openai_errors_total[5m]))
/ sum(rate(skuel_openai_requests_total[5m]))
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

#### Deepgram Transcription Metrics (1 metric + duration)

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `skuel_transcription_requests_total` | Counter | `status` | Total transcription requests |
| `skuel_transcription_duration_seconds` | Histogram | - | Transcription time |

**Statuses**: `success`, `failed`
**Duration Buckets**: `(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)`

**Example Queries**:
```promql
# Transcription request rate
rate(skuel_transcription_requests_total[5m])

# p95 transcription latency
histogram_quantile(0.95, rate(skuel_transcription_duration_seconds_bucket[5m]))
```

**Instrumentation Locations**:
- OpenAI calls: `core/services/neo4j_genai_embeddings_service.py:138-160`
- Embedding worker: `core/services/background/embedding_worker.py:165-180`
- Updated in services_bootstrap: `core/utils/services_bootstrap.py:588-590`

**Key Alerts** (see `ALERTING.md`):
- `HighOpenAIErrorRate` - >20% API failures
- `EmbeddingQueueBacklog` - >500 pending items
- `HighEmbeddingFailureRate` - >20% failed embeddings
- `SlowOpenAICalls` - p95 >30s

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
3. **Active Entities**: `skuel_active_entities_count` gauge
4. **Completion Percentage**: `(completed / created) * 100`
5. **User Engagement Heatmap**: Creation events by hour/day

**Use Case**: Track feature adoption, monitor user engagement, identify trends

### 3. Graph Health Dashboard

**File**: `/monitoring/grafana/dashboards/graph_health.json`
**Focus**: Relationship patterns and graph integrity

**Key Panels**:
1. **Graph Density**: `skuel_graph_density` (higher = more connected)
2. **Orphaned Entities**: `skuel_orphaned_entities_count` (target: 0)
3. **Relationship Breakdown by Layer**: `skuel_relationships_count` stacked by layer
4. **Blocking Dependencies**: `skuel_blocking_relationships_count`
5. **Dependency Chain Length**: `skuel_dependency_chain_max_length` (detect deep chains)
6. **Cross-Domain Connections**: `skuel_cross_domain_relationships_count` heatmap

**Use Case**: Ensure graph integrity, optimize relationship structure, detect anomalies

### 4. User Journey Dashboard

**File**: `/monitoring/grafana/dashboards/user_journey.json`
**Focus**: Event flow and processing

**Key Panels**:
1. **Event Publication Rate**: `rate(skuel_events_published_total[5m])`
2. **Event Handler Latency**: `skuel_event_handler_duration_seconds` histogram
3. **Slow Event Handlers**: Top 5 by p95 latency
4. **Event Handler Errors**: `skuel_event_handler_errors_total`
5. **Context Invalidations**: `rate(skuel_context_invalidations_total[5m])`

**Use Case**: Debug event processing, optimize handler performance, track invalidations

---

## Common Workflows

### Verify Metrics Are Populating

```bash
# 1. Check /metrics endpoint
curl http://localhost:5001/metrics | grep skuel_http_requests_total

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
   - Legend format: `{{user_uid}}`
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
| `/core/infrastructure/monitoring/prometheus_metrics.py` | **Canonical metric definitions** (35 metrics, 8 classes) |
| `/core/infrastructure/monitoring/metrics_cache.py` | In-memory cache for debugging (optional, lossy) |
| `/core/infrastructure/monitoring/metrics_event_handler.py` | Domain event subscriptions for entity tracking |
| `/core/infrastructure/monitoring/http_instrumentation.py` | HTTP request instrumentation |
| `/adapters/inbound/metrics_routes.py` | `/metrics` endpoint for Prometheus scraper |
| `/monitoring/prometheus/prometheus.yml` | Prometheus scrape configuration (15s interval) |
| `/monitoring/grafana/dashboards/*.json` | 4 production dashboards |
| `/docker-compose.yml` | Development stack (Prometheus + Grafana services) |

---

## Related Skills

- **[python](../python/SKILL.md)** - Python patterns and protocols
- **[result-pattern](../result-pattern/SKILL.md)** - Result[T] error handling
- **[neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md)** - Graph query patterns
- **[base-analytics-service](../base-analytics-service/SKILL.md)** - Analytics without AI

---

## See Also

- [PROMQL_PATTERNS.md](PROMQL_PATTERNS.md) - PromQL query examples from dashboards
- [INSTRUMENTATION.md](INSTRUMENTATION.md) - How to add metrics to features
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues and debugging
- `/docs/observability/PROMETHEUS_METRICS.md` - Comprehensive 966-line reference
- `/docs/decisions/ADR-036-prometheus-primary-cache-pattern.md` - Architecture rationale
