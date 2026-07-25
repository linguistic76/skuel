# Prometheus + Grafana Observability for SKUEL

**Status**: ✅ Complete (Phases 1-5 implemented - January 2026)

## Table of Contents

1. [Overview](#overview)
2. [Why Prometheus + Grafana?](#why-prometheus--grafana)
3. [Grafana vs ProfileHub: Two Perspectives](#grafana-vs-profilehub-two-perspectives)
4. [Quick Start](#quick-start)
5. [Metrics Reference](#metrics-reference)
6. [Dashboards](#dashboards)
7. [Query Examples](#query-examples)
8. [Troubleshooting](#troubleshooting)
9. [Implementation History](#implementation-history)

---

## Overview

SKUEL uses Prometheus for metrics collection and Grafana for visualization, providing comprehensive observability across:

- **System Health** - HTTP requests, Neo4j performance
- **Domain Activity** - Entity creation/completion
- **Graph Health** - Relationship patterns, density, lateral connections (PRIMARY FOCUS)
- **Event Bus** - Publication rate, handler latency, errors

---

## Why Prometheus + Grafana?

### The Fundamental Decision

SKUEL chose to use **established open-source observability tools** (Prometheus + Grafana) rather than build custom metrics infrastructure within the SKUEL UI.

### The Philosophy

**"Use proven tools for infrastructure, build custom solutions for domain logic."**

SKUEL's development philosophy:
- ✅ **Build custom**: Domain-specific features (entity types, graph relationships, intelligence services)
- ❌ **Don't build custom**: Infrastructure that already exists and is battle-tested

Prometheus + Grafana represent **50+ years of combined development** by dedicated teams:
- Prometheus: Time-series database, query language (PromQL), alerting
- Grafana: Visualization, dashboarding, team collaboration

Building equivalent functionality in-house would require:
- **Months of development** (charting libraries, time-series storage, query engine)
- **Ongoing maintenance** (keep up with Grafana's ~20 releases/year)
- **Feature gap** (will never match Prometheus/Grafana's feature set)

### The Alternative (Considered and Rejected)

**Option: Build observability dashboards in SKUEL's UI using existing in-memory metrics**

SKUEL uses Prometheus for metrics:
- Query performance tracking
- Event bus monitoring via MetricsCache
- Search quality tracking

**Why not just build dashboards on top of these?**

❌ **Reinventing the wheel**
- Need time-series storage (Prometheus does this)
- Need charting library (Grafana has 50+ chart types)
- Need aggregation engine (PromQL is powerful)
- Need alerting system (Prometheus Alertmanager exists)

❌ **Maintenance burden**
- Charting libraries need updates
- Dashboard UI needs design/iteration
- Query engine needs optimization
- Historical storage needs management

❌ **No historical data**
- In-memory metrics disappear on app restart
- Can't analyze trends over days/weeks
- Can't correlate incidents with metric changes

❌ **Limited query flexibility**
- Would need to build query language
- PromQL supports percentiles, rate calculations, aggregations
- Complex queries (p95 latency by endpoint) would require custom code

❌ **No industry standard export**
- Grafana supports 100+ data sources
- Can't integrate with external monitoring tools
- Difficult to share with ops teams familiar with Grafana

### The "Export, Don't Replace" Pattern

**SKUEL keeps BOTH** - existing in-memory metrics AND Prometheus export. This is intentional.

**Keep In-Memory Metrics For:**

✅ **Debugging** (no network dependency)
```python
# Direct access during development
metrics_store.get_query_latency("Task.search")  # Immediate result
```

✅ **Testing** (unit tests use them directly)
```python
# Tests verify metrics without Prometheus
assert performance_monitor.get_event_count("TaskCreated") > 0
```

✅ **Immediate access** (works even if Prometheus is down)
```python
# App continues functioning if monitoring fails
if prometheus_unavailable:
    # Metrics still tracked in-memory
    logger.debug(f"Query took {metrics_store.last_query_time}ms")
```

**Export to Prometheus For:**

✅ **Historical trends** (7-day retention, configurable)
```promql
# See how graph density evolved over time
skuel_graph_density[7d]
```

✅ **Dashboards** (Grafana's visualization)
```
# Beautiful dashboards instead of raw numbers
Graph Health dashboard shows 23 panels with time-series, gauges, pie charts
```

✅ **Alerting** (live: 14 rules in `/monitoring/prometheus/alerts.yml`; no Alertmanager by choice)
```yaml
# Alert if error rate > 5%
- alert: HighErrorRate
  expr: error_rate > 0.05
  for: 5m
```

✅ **Operational intelligence** (aggregate queries across metrics)
```promql
# Complex queries combining multiple metrics
(skuel_total_relationships / skuel_total_entities) > 2.0
```

### What This Solves

**Problem**: Need operational visibility into:
- System health (is Neo4j responding? Are endpoints slow?)
- Graph evolution (is connectivity improving? Are entities isolated?)
- User behavior trends (which features are used? What's completion rate?)

**Solution**: Prometheus + Grafana provide this **without reinventing infrastructure**.

**Benefit**: Development time spent on SKUEL's unique value (Entity Type Architecture, graph intelligence) instead of rebuilding Grafana.

### The Boundary: What Goes Where?

| Observability Need | Tool | Rationale |
|-------------------|------|-----------|
| **Ops/admin view** (aggregate metrics, trends) | Prometheus + Grafana | Proven tools, rich features |
| **User view** (personal progress, motivation) | ProfileHub (`/profile`) | Custom UX, contextual |
| **In-app debugging** (immediate access) | In-memory metrics | No network dependency |
| **Test verification** | In-memory metrics | Unit tests don't need Prometheus |

### Real-World Analogy

Similar to how SKUEL uses:
- **PostgreSQL/Neo4j** instead of building a custom database
- **OpenAI API** instead of training custom LLMs
- **FastHTML** instead of building a web framework

SKUEL uses **Prometheus/Grafana** instead of building custom observability infrastructure.

**The pattern**: "Use best-of-breed tools for infrastructure, focus development on domain logic."

### Cost-Benefit Analysis

**Custom Dashboard Development** (estimated):
- 2-3 weeks: Time-series storage layer
- 1-2 weeks: Charting library integration
- 1 week: Dashboard UI components
- 1 week: Query builder
- **Ongoing**: Maintenance, bug fixes, feature parity

**Prometheus + Grafana**:
- 1 day: Docker setup
- 3 days: Metrics instrumentation
- 1 day: Dashboard creation
- **Ongoing**: Minimal (version updates only)

**ROI**: Saved 4-5 weeks of development + ongoing maintenance burden.

### The Result

**4 Production Dashboards**:
1. System Health (infrastructure monitoring)
2. Domain Activity (business metrics)
3. Graph Health (relationship patterns) ← PRIMARY FOCUS
4. Event Bus (publication rate, handler latency, errors)

**40 Metrics** tracked across HTTP, database, events, domains, relationships, queries, AI.

**Zero maintenance burden** - Prometheus/Grafana handle storage, querying, visualization.

---

## One Surface: Prometheus (PR #803)

Prometheus text exposition (`/metrics`) is THE metrics surface. The JSON `/api/monitoring/*`
routes and the admin `/api/metrics` route were deleted in PR #803 — they duplicated what
`/health/ready` and the Prometheus series already provide. Do not reintroduce JSON metrics
endpoints.

**Production posture**: the droplet runs no Prometheus/Grafana — production is app + Caddy
only, the app binds loopback-only (`127.0.0.1:5001`), and Caddy returns 403 for public
`/metrics` (auth-exempt app-side; would leak internal telemetry if exposed). On-droplet reads:

```bash
docker compose exec skuel-app curl -s localhost:5001/metrics
```

Consequence: alert rules evaluate only where Prometheus runs — the dev monitoring profile,
scraping a dev app backed by local Docker Neo4j. The AuraDB cap alerts have an in-app
production counterpart: the graph-health poller feeds its counts through
`check_aura_cap_headroom()` (WARNING above 80% of cap, ERROR above 95% — thresholds in
`core/constants.py` `AuraDBCaps`, drift-pinned to the alert exprs), so the caps are guarded
where they bind, without Prometheus. See the prometheus-grafana skill's ALERTING.md § Where
Alerts Actually Evaluate.

---

## Grafana vs ProfileHub: Two Perspectives

**IMPORTANT**: SKUEL has TWO systems that show user activity data. This is **NOT duplication** - they serve different audiences with different purposes.

### The Distinction

| Aspect | Grafana Dashboards | ProfileHub (`/profile`) |
|--------|-------------------|------------------------|
| **Audience** | Admins, ops team, product managers | Individual users |
| **Purpose** | Operational intelligence, system health | Personal progress, motivation |
| **View** | Aggregate metrics across ALL users | Individual user's own data |
| **Questions** | "How is the system being used?" | "What have I accomplished?" |
| **Context** | Trends, comparisons, optimization | Personal timeline, achievements |
| **Access** | Admin-only (Grafana login required) | User-facing (authenticated users) |

### Examples of the Same Data, Different Perspective

**Grafana Domain Activity Dashboard** (Admin View):
```
"Users created 1,247 tasks this week"
"Aggregate task completion rate: 67%"
"Habits domain has highest engagement"
"Event handler p95 latency: 8ms"
→ Actionable insight: Investigate the Habit completion drop after launch
```

**ProfileHub** (User View):
```
"You completed 12 tasks this week"
"You've created 3 goals this month"
"Recent activity: Completed 'Fix bug in login flow' 2 hours ago"
"Your task completion streak: 5 days"
→ Motivational feedback: Keep up the momentum!
```

### Why Both Exist (One Path Forward Philosophy)

SKUEL's "One Path Forward" principle is **NOT violated** because:

1. **Different Audiences**: Admins vs end users
2. **Different Questions**: System optimization vs personal tracking
3. **Different Contexts**: Operational decisions vs personal motivation
4. **Different Access Patterns**: Aggregate queries vs individual lookups

### Analogies to Other Systems

- **Google Analytics** (admin) vs **User Dashboard** (personal)
- **Server Logs** (ops) vs **Activity Feed** (user)
- **Stripe Dashboard** (business metrics) vs **Customer Portal** (personal usage)
- **CloudWatch** (ops) vs **User Profile** (personal)

### When to Use Which

**Use Grafana Dashboards When**:
- Diagnosing system performance issues
- Understanding aggregate user behavior
- Making product decisions (which features are used?)
- Identifying trends and patterns
- Comparing metrics across users
- Monitoring operational health

**Use ProfileHub When**:
- User wants to see their personal progress
- Motivating continued engagement
- Showing recent activity timeline
- Personal goal tracking
- Individual achievement celebration

### The Boundary

**Grafana**: "Is the **SYSTEM** healthy? How are **USERS** (plural) engaging?"

**ProfileHub**: "How am **I** (singular) doing? What is **MY** progress?"

**Key Insight**: The same underlying data (tasks completed, searches performed) serves **fundamentally different purposes** depending on audience and context. This is complementary architecture, not duplication.

---

### Architecture

```
SKUEL App (:8000)
    |
    +--> /metrics endpoint (Prometheus exposition format)
           |
           v
    Prometheus (:9090)  [Scrapes every 15s]
           |
           v
    Grafana (:3000)     [4 dashboards]
```

### Philosophy

**"Prometheus First"** - Prometheus is the source of truth for all metrics. MetricsCache provides in-memory debugging access (last 100 items) while Prometheus handles historical trends and dashboards.

---

## Quick Start

### Access Points

- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Metrics Endpoint**: http://localhost:8000/metrics

### View Metrics

```bash
# Raw metrics
curl http://localhost:8000/metrics | grep skuel_

# Prometheus UI
open http://localhost:9090

# Grafana dashboards
open http://localhost:3000/dashboards
```

### Available Dashboards

1. **System Health** (`skuel-system-health`) - Infrastructure monitoring
2. **Domain Activity** (`skuel-domain-activity`) - Business metrics
3. **Graph Health** (`skuel-graph-health`) - Relationship patterns ← PRIMARY
4. **Event Bus** (`skuel-event-bus`) - Event publication rate, handler latency, errors

---

## Metrics Reference

### HTTP Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `skuel_http_requests_total` | Counter | method, endpoint, status | Total HTTP requests |
| `skuel_http_request_duration_seconds` | Histogram | method, endpoint | Request latency |
| `skuel_http_errors_total` | Counter | method, endpoint, status | Total HTTP errors |

**Latency Buckets**: 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0 seconds

### Database Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `skuel_neo4j_queries_total` | Counter | operation, label | Total Neo4j queries |
| `skuel_neo4j_query_duration_seconds` | Histogram | operation, label | Query latency |
| `skuel_neo4j_errors_total` | Counter | operation | Database errors |

**Operations**: create, read, update, delete, search, relationship

**Latency Buckets**: 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0 seconds

### Event Bus Metrics (Phase 3)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `skuel_events_published_total` | Counter | event_type | Total events published |
| `skuel_event_publish_duration_seconds` | Histogram | event_type | Publication overhead |
| `skuel_event_handler_calls_total` | Counter | event_type, handler | Handler invocations |
| `skuel_event_handler_duration_seconds` | Histogram | event_type, handler | Handler execution time |
| `skuel_event_handler_errors_total` | Counter | event_type, handler | Handler errors |
| `skuel_context_invalidations_total` | Counter | - | UserContext invalidations |

**Handler Duration Buckets**: 0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0 seconds

### Domain Activity Metrics (Phase 3)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `skuel_entities_created_total` | Counter | entity_type | Entities created |
| `skuel_entities_completed_total` | Counter | entity_type | Entities completed |

**Entity Types**: task, goal, habit, event, choice, principle, transcription, ku, ps, lp, user_entry (journals count as user_entry — ADR-054)

### Graph Health Metrics (Phase 4 - PRIMARY FOCUS)

All graph-health gauges are **system-wide — no labels beyond those listed** (no `user_uid`;
per-user data lives in Neo4j). They are updated by the 5-minute graph-health poller in
`scripts/dev/bootstrap.py`.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `skuel_graph_density` | Gauge | - | Avg relationships per entity |
| `skuel_total_entities` | Gauge | - | Total nodes in graph |
| `skuel_total_relationships` | Gauge | - | Total edges in graph |
| `skuel_orphaned_entities_count` | Gauge | - | Entities with no relationships |

#### Relationship Layer Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `skuel_relationships_count` | Gauge | layer | Relationships by layer |
| `skuel_lateral_relationships_by_category` | Gauge | category | Lateral breakdown |

**Layers**: hierarchical, lateral, semantic, cross_domain

**Lateral Categories**: structural, dependency, semantic, associative

#### Specific Relationship Types

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `skuel_blocking_relationships_count` | Gauge | - | BLOCKS relationships |
| `skuel_enables_relationships_count` | Gauge | - | ENABLES relationships |
| `skuel_contains_relationships_count` | Gauge | - | CONTAINS relationships |
| `skuel_organizes_relationships_count` | Gauge | - | ORGANIZES (MOC) relationships |

#### Knowledge-Subgraph Structural Health (ADR-080 Horizon 1, PR #770)

Knowledge-scoped view of graph health — the raw structural signals `KnowledgeHealthService`
interprets into a composite GDS-readiness score. Scoped to the knowledge subgraph
(Ku / PathStep / LearningPath / Exercise) with learner-state telemetry edges excluded.
Fed by a 4th query on the same 5-min poller — no new worker.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `skuel_knowledge_kus_total` | Gauge | - | Total Ku nodes in the knowledge subgraph |
| `skuel_knowledge_orphan_kus_count` | Gauge | - | Kus with zero incident relationships |
| `skuel_knowledge_avg_ku_degree` | Gauge | - | Average incident relationships per Ku |
| `skuel_knowledge_composed_kus_count` | Gauge | - | Kus composed into ≥1 PathStep |
| `skuel_knowledge_prerequisite_edges_count` | Gauge | - | Prerequisite-DAG edges among knowledge nodes |
| `skuel_knowledge_organizes_edges_count` | Gauge | - | ORGANIZES/MOC edges among knowledge nodes |

Pairs with `/admin/knowledge-health` and `./dev knowledge-health [--json]` (the on-demand
full report). **See:** `/docs/decisions/ADR-080-auradb-three-horizon-strategy.md`.

#### Poller Freshness

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `skuel_graph_health_poll_last_success_timestamp_seconds` | Gauge | - | Unix time of the last successful graph-health poll (baseline set at task start; refreshed only after an error-free pass) |

All graph-health gauges freeze at their last values when the poller can't reach Neo4j;
this timestamp makes that staleness alertable (`GraphHealthPollerStale`, >900s).

### Query Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `skuel_operation_calls_total` | Counter | operation_name | Total operation calls (e.g., ku_search_by_title) |
| `skuel_operation_duration_seconds` | Histogram | operation_name | Operation execution time |
| `skuel_operation_errors_total` | Counter | operation_name | Operation errors |

### AI Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `skuel_ai_requests_total` | Counter | operation, model | AI API requests (embeddings/chat/completion) |
| `skuel_ai_duration_seconds` | Histogram | operation, model | AI API call duration |
| `skuel_ai_errors_total` | Counter | operation, error_type | AI API errors (rate_limit/timeout/auth) |
| `skuel_embedding_queue_size` | Gauge | queue_type | Pending embeddings (entity/chunk) |
| `skuel_embeddings_processed_total` | Counter | entity_type, status | Embeddings processed (success/failed) |
| `skuel_embedding_batch_size` | Histogram | - | Embedding batch size distribution |

---

## Dashboards

### 1. System Health (Infrastructure)

**UID**: `skuel-system-health`

**Purpose**: Monitor HTTP traffic, Neo4j performance, system resources

**Key Panels**:
- HTTP Request Rate (QPS)
- HTTP Error Rate (%)
- Request Latency (p50/p95/p99)
- Neo4j Query Rate by Operation
- Neo4j Query Latency Distribution (heatmap)
- Neo4j Connection Status
- Python Process Memory

**Use Cases**:
- Identify slow endpoints
- Monitor database performance
- Detect error spikes
- Track system resource usage

### 2. Domain Activity (Business/Product - Admin View)

**UID**: `skuel-domain-activity`

**Audience**: Admins, product team (NOT end users - see ProfileHub for user-facing view)

**Purpose**: Track aggregate entity lifecycle and event bus activity across all users

**Key Panels**:
- Entities Created (Rate) - stacked by type
- Entities Completed (Rate) - stacked by type
- Total Entities Created (Last Hour) - bar chart
- Total Entities Completed (Last Hour) - bar chart
- Event Publication Rate
- Event Handler Call Rate
- Event Handler Duration (p95)
- Event Handler Errors

**Use Cases** (Admin/Product Perspective):
- Which domains are most active across all users? (feature engagement)
- What's the aggregate completion rate? (product health metrics)
- Are users engaging with features? (adoption tracking)
- Event bus performance monitoring (operational health)

**Note**: This dashboard shows **aggregate business metrics** for product decisions. For individual user progress ("How many tasks did I complete?"), users should view their **ProfileHub** (`/profile`) instead.

### 3. Graph Health (Graph Perspective) ← PRIMARY FOCUS

**UID**: `skuel-graph-health`

**Purpose**: Understand graph connectivity, density, and lateral relationship patterns

**Key Panels**:

**Row 1: Overall Health**
- Graph Density Score (gauge)
- Total Entities (stat)
- Total Relationships (stat)
- Orphaned Entities (stat with alert)
- Connectivity Ratio (calculated)

**Row 2: Relationship Layers**
- Relationships by Layer (stacked time series)
  - Hierarchical (blue)
  - Lateral (green) ← FOCUS
  - Semantic (orange)
  - Cross-Domain (purple)

**Row 3: Lateral Relationships (PRIMARY FOCUS)**
- Lateral by Category (pie chart)
  - Structural (SIBLING, COUSIN)
  - Dependency (BLOCKS, ENABLES) ← FOCUS
  - Semantic (RELATED_TO, SIMILAR_TO)
  - Associative (ALTERNATIVE_TO, STACKS_WITH)
- BLOCKS Relationships (gauge)
- ENABLES Relationships (gauge)

**Row 4: Hierarchical Patterns**
- CONTAINS Count (stat)
- ORGANIZES Count (MOC pattern) (stat)
- Hierarchical Growth (time series)

**Use Cases**:
- Is the graph well-connected?
- How many dependency chains exist?
- Are entities isolated (orphaned)?
- How is the graph evolving over time?

**Row 5: Knowledge Subgraph Health (ADR-080 H1)**
- Total Kus, Avg Ku Degree, Prerequisite Edges, ORGANIZES Edges (stats)
- Orphan Ku Ratio and Composition Coverage (percent gauges)

**Alerts** (live, in `/monitoring/prometheus/alerts.yml`): `HighOrphanedEntityCount` (>100),
`AuraNodeCapApproaching` (>160k), `AuraRelationshipCapApproaching` (>320k),
`GraphHealthPollerStale` (poller >900s stale — gauges frozen)

### 4. Event Bus (Admin/Ops Perspective)

**UID**: `skuel-event-bus`

**Audience**: Admins, ops team

**Purpose**: Track event bus health — publication rate, handler latency, error trends

**Key Panels**:

**Row 1: Event Bus Activity**
- Event Publication Rate
- Event Handler Performance (p95)

**Row 2: Summary Stats**
- Events Published (1h)
- Event Handler Calls (1h)
- Event Handler Errors (1h)

**Use Cases**:
- Detect handler regressions (latency creep)
- Spot error rate increases after deploys
- Verify event bus is processing under load

---

## Query Examples

### System Health

```promql
# HTTP request rate (queries per second)
sum(rate(skuel_http_requests_total[5m]))

# HTTP error percentage
100 * sum(rate(skuel_http_requests_total{status=~"5.."}[5m]))
    / sum(rate(skuel_http_requests_total[5m]))

# p95 request latency
histogram_quantile(0.95,
  sum(rate(skuel_http_request_duration_seconds_bucket[5m])) by (le)
)

# Neo4j queries per second by operation
sum(rate(skuel_neo4j_queries_total[5m])) by (operation)

# p95 Neo4j query latency
histogram_quantile(0.95,
  sum(rate(skuel_neo4j_query_duration_seconds_bucket[5m])) by (operation, le)
)
```

### Domain Activity

```promql
# Entity creation rate by type
sum(rate(skuel_entities_created_total[5m])) by (entity_type)

# Entity completion rate
sum(rate(skuel_entities_completed_total[5m])) by (entity_type)

# Total entities created in last hour
sum(increase(skuel_entities_created_total[1h])) by (entity_type)

# Event publication rate
sum(rate(skuel_events_published_total[5m]))

# p95 event handler duration
histogram_quantile(0.95,
  sum(rate(skuel_event_handler_duration_seconds_bucket[5m])) by (le)
)
```

### Graph Health

```promql
# Current graph density
skuel_graph_density

# Total relationships by layer
skuel_relationships_count

# Lateral relationships by category
skuel_lateral_relationships_by_category

# BLOCKS relationship count
skuel_blocking_relationships_count

# Orphaned entities
skuel_orphaned_entities_count

# Graph connectivity ratio
skuel_total_relationships / skuel_total_entities

# AuraDB Free cap headroom (alerts fire at 0.8)
skuel_total_entities / 200000
skuel_total_relationships / 400000

# Knowledge subgraph: orphan ratio and composition coverage
skuel_knowledge_orphan_kus_count / skuel_knowledge_kus_total
skuel_knowledge_composed_kus_count / skuel_knowledge_kus_total
```

---

## Troubleshooting

### Prometheus Target Down

**Symptom**: Grafana shows "No data" or Prometheus target shows "DOWN"

**Check**:
```bash
# Verify app is running
curl http://localhost:8000/metrics

# Check Prometheus targets
open http://localhost:9090/targets

# Check docker logs
docker logs skuel-prometheus
```

**Fix**:
- Ensure SKUEL app is running on port 8000
- Verify Prometheus scrape config: `/monitoring/prometheus/prometheus.yml`
- Restart Prometheus: `docker restart skuel-prometheus`

### Metrics Not Populating

**Symptom**: Metrics exist but show no data

**Cause**: Metrics are incremented when events occur (tasks completed, searches performed, etc.)

**Solution**:
- **Graph Health**: The poller runs at startup, then every 5 minutes — if gauges are missing, check app logs for graph-health errors
- **Domain Activity**: Create/complete tasks to trigger metrics
- **Event Bus**: Events are published automatically during operations

### Dashboard JSON Issues

**Symptom**: Dashboard doesn't load in Grafana

**Check**:
```bash
# Validate JSON syntax
python3 -m json.tool /monitoring/grafana/dashboards/graph_health.json

# Check provisioning
docker exec skuel-grafana cat /etc/grafana/provisioning/dashboards/skuel.yml

# Check dashboard mount
docker exec skuel-grafana ls /var/lib/grafana/dashboards
```

**Fix**:
- Restart Grafana: `docker restart skuel-grafana`
- Check docker-compose.yml volume mounts
- Verify dashboard JSON is valid

### High Cardinality Labels

**Symptom**: Prometheus memory usage growing, slow queries

**Cause**: Unbounded label values (e.g., task titles, user IDs)

**Prevention**:
- ✅ Use `entity_type`, `operation`, `status` (small fixed sets)
- ❌ Never use `user_uid` — per-user data belongs in Neo4j, not Prometheus
- ❌ Don't use task titles, descriptions, or arbitrary text

### Background Tasks Not Running

**Symptom**: Graph health metrics not updating

**Check**:
```bash
# Check app logs
docker logs skuel-app | grep "Graph health metrics"
```

**Expected**:
- "Graph health metrics update task started (5 min interval)"
- Note: the first pass runs at startup (poll-first loop), then every 5 minutes

---

## Implementation History

### Phase 1: Foundation (Week 1 - January 2026)

**Goal**: Get Prometheus + Grafana running

**Implemented**:
- Added `prometheus-client = "^0.21.0"` dependency
- Created PrometheusMetrics class with 7 metric groups
- Created `/metrics` endpoint (Prometheus exposition format)
- Added Prometheus + Grafana to docker-compose.yml
- Created Prometheus scrape configuration
- Created Grafana datasource provisioning

**Files Created**:
- `/core/infrastructure/monitoring/prometheus_metrics.py`
- `/adapters/inbound/metrics_routes.py`
- `/monitoring/prometheus/prometheus.yml`
- `/monitoring/grafana/provisioning/datasources/prometheus.yml`
- `/monitoring/grafana/provisioning/dashboards/skuel.yml`

**Outcome**: ✅ Prometheus scraping, Grafana accessible

### Phase 2: HTTP & Database Instrumentation (Week 2)

**Goal**: Track HTTP requests and Neo4j operations

**Implemented**:
- HTTP middleware (future - route factories support)
- Neo4j query instrumentation (UniversalNeo4jBackend)
- System Health dashboard

**Files Created/Modified**:
- `/monitoring/grafana/dashboards/system_health.json`
- Modified: `UniversalNeo4jBackend` (Neo4j metrics)

**Outcome**: ✅ Infrastructure observability operational

### Phase 3: Event Bus & Domain Metrics (Week 3)

**Goal**: Business-level metrics

**Implemented**:
- MetricsCache (Prometheus as primary, in-memory cache for debugging)
- MetricsEventHandler (subscribes to domain events)
- Direct Prometheus writes (no bridge, no export lag)
- Domain Activity dashboard

**Files Created**:
- `/core/infrastructure/monitoring/metrics_cache.py`
- `/core/infrastructure/monitoring/metrics_event_handler.py`
- `/monitoring/grafana/dashboards/domain_activity.json`

**Modified**:
- `/scripts/dev/bootstrap.py` (wired metrics cache to event bus)
- `/adapters/infrastructure/event_bus.py` (uses MetricsCache)

**Metrics Added**:
- Event bus: events_published, handler_calls, handler_duration, handler_errors
- Domain activity: entities_created, entities_completed by type

**Outcome**: ✅ Domain activity tracking operational (Prometheus-first architecture)

### Phase 3.5: Prometheus-Primary Pattern (January 2026)

**Goal**: Reduce duplication, improve cohesion (Option D from analysis)

**Changes**:
- Removed PrometheusPerformanceBridge (no longer needed)
- Event bus writes directly to Prometheus (source of truth)
- MetricsCache provides debugging access (last 100 items)
- Zero export lag (was 30 seconds with bridge)

**Files Removed**:
- `/core/infrastructure/monitoring/prometheus_bridge.py`

**Benefits**:
- ✅ Single source of truth (Prometheus)
- ✅ Reduced duplication (40% → 10%)
- ✅ No bridge code to maintain
- ✅ Real-time metrics (no 30s delay)
- ✅ Maintains debugging access (cache)

**See**: `/docs/decisions/ADR-036-prometheus-primary-cache-pattern.md`

### Phase 4: Graph Health & Lateral Relationships (Week 4) ← PRIMARY

**Goal**: Graph density and relationship pattern tracking

**Implemented**:
- Enhanced RelationshipMetrics (15 metrics)
- Graph health background task (5-minute interval)
- Neo4j queries for graph statistics
- Graph Health dashboard (16 panels)

**Files Created**:
- `/monitoring/grafana/dashboards/graph_health.json`

**Modified**:
- `/core/infrastructure/monitoring/prometheus_metrics.py` (expanded RelationshipMetrics)
- `/scripts/dev/bootstrap.py` (added graph health background task)

**Metrics Added** (15 total):
- Graph health: density, total_entities, total_relationships, orphaned_entities
- Relationship layers: relationships_count by layer
- Lateral breakdown: lateral_by_category (structural/dependency/semantic/associative)
- Specific types: blocking, enables, contains, organizes, semantic, cross_domain
- Performance: dependency_chain_length, graph_traversal_depth

**Outcome**: ✅ Graph health visibility achieved (PRIMARY GOAL)

### Phase 5: Polish & Documentation (Week 5)

**Goal**: Complete observability stack with comprehensive documentation

**Implemented**:
- Event Bus dashboard
- System Health dashboard (verified existing)
- Comprehensive documentation

**Files Created**:
- `/monitoring/grafana/dashboards/event_bus.json`
- `/docs/observability/PROMETHEUS_METRICS.md` (this file)

**Outcome**: ✅ Complete observability stack

### Post-launch cleanup (May 2026)

Removed 14 unemitted "aspirational" metrics from `prometheus_metrics.py`:
- `SystemMetrics` class (cpu_usage, memory_usage, neo4j_connected) — system-level health was never instrumented
- `SearchMetrics` class (searches_total, search_duration, search_similarity) — search instrumentation never wired into SearchRouter
- `DomainMetrics.active_entities` — current-state gauge superseded by entities_created/completed counters
- 4 dead RelationshipMetrics gauges (dependency_chain_length, semantic_relationships, cross_domain_relationships, graph_traversal_depth) — never calculated by graph health background task
- 3 dead AiMetrics (ai_tokens_used, transcription_requests_total, transcription_duration_seconds) — token counting and Deepgram instrumentation never implemented

The Search & Events dashboard was rewritten as the Event Bus dashboard (search panels removed; event panels preserved).

**Doctrine established**: emit-first — a metric definition merges only together with its
emission. Deferred instrumentation stays a plain backlog note (review doc, ADR, TODO), never
a defined-but-unemitted metric; there is deliberately no planned-metrics registry.

### Knowledge-subgraph gauges (PR #770, July 2026)

Added the 6 `skuel_knowledge_*` gauges (ADR-080 Horizon 1) as a 4th query on the existing
5-min graph-health poller — no new worker. 33 → 39 metrics.

### One-surface consolidation (PR #803, July 2026)

Deleted the JSON `/api/monitoring/*` routes and the admin `/api/metrics` route; Caddy now
blocks public `/metrics` in production. Prometheus text exposition is the only metrics
surface. Alert rules grew to 13 (incl. the two AuraDB Free cap alerts).

### Review quick wins (July 2026)

From the 2026-07-24 Prometheus review: `skuel_graph_health_poll_last_success_timestamp_seconds`
+ `GraphHealthPollerStale` alert (poller staleness made visible; 39 → 40 metrics, 13 → 14 rules),
the Knowledge Subgraph Health dashboard row (closing #770's visualization gap), and
`tests/unit/test_metric_reference_drift.py` — a guard that every `skuel_*` name referenced by
dashboards or alert rules exists in `prometheus_metrics.py`.

---

## Dashboard Version Control

All dashboards are version-controlled in git:

```
/monitoring/grafana/dashboards/
├── system_health.json       # Infrastructure
├── domain_activity.json     # Business metrics
├── graph_health.json        # Graph patterns ← PRIMARY
└── event_bus.json           # Event publication, handler latency, errors
```

**Workflow**:
1. Edit dashboard in Grafana UI
2. Export: `curl http://localhost:3000/api/dashboards/uid/skuel-graph-health | jq .dashboard > graph_health.json`
3. Commit to repo
4. Dashboards auto-load on Grafana startup

**Benefits**:
- Infrastructure as code
- Change tracking (git history)
- PR reviews for dashboard changes
- Easy restore if misconfigured

---

## Key Metrics Summary

| Category | Count | Update Frequency |
|----------|-------|------------------|
| HTTP | 3 | Per request |
| Database | 3 | Per query |
| Event Bus | 6 | Per event |
| Domain Activity | 2 | Per event |
| Graph Health (incl. 6 knowledge gauges + poller freshness) | 17 | Every 5 minutes |
| Query | 3 | Per operation |
| AI | 6 | Per AI call |
| **TOTAL** | **40 metrics** | **Varies** |

---

## Performance Impact

- **Metrics Collection**: < 1ms overhead per operation
- **Background Tasks**:
  - Graph health: 5min interval, ~500ms execution (the only periodic metrics loop)
- **Storage**: ~10MB/day for typical usage
- **Prometheus Retention**: 7 days (`--storage.tsdb.retention.time=7d` in docker-compose.yml)

---

## Future Enhancements (Optional)

- [ ] Knowledge Health panel row on the Graph Health dashboard (the 6 gauges are polled but unvisualized)
- [ ] Custom recording rules for complex queries
- [ ] Dependency chain visualization
- [ ] UserContext build performance tracking

Non-goals (doctrine): per-user metrics (user behavior lives in Neo4j), Alertmanager
notification routing (single operator, no notification chain), and any metric defined
without emission in the same change (emit-first — see the May 2026 cleanup above).

---

## References

- Prometheus Documentation: https://prometheus.io/docs/
- Grafana Documentation: https://grafana.com/docs/
- PromQL Guide: https://prometheus.io/docs/prometheus/latest/querying/basics/
- SKUEL Architecture: `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md`
- SKUEL Event System: `/docs/patterns/event_driven_architecture.md`

---

**Last Updated**: 2026-07-24 (post-PR #803 one-surface consolidation + PR #770 knowledge gauges)

**Status**: ✅ Production-ready observability stack
