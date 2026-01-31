# PromQL Query Patterns

> Real PromQL queries extracted from SKUEL's production Grafana dashboards

This guide contains battle-tested PromQL queries for common observability tasks. All queries are taken from actual SKUEL dashboards.

## HTTP Metrics Queries

### Request Rate (QPS)

```promql
# Total requests per second
rate(skuel_http_requests_total[5m])

# By endpoint
sum by (endpoint) (rate(skuel_http_requests_total[5m]))

# By method and status
sum by (method, status) (rate(skuel_http_requests_total[5m]))

# Success rate (non-error responses)
sum(rate(skuel_http_requests_total{status!~"5.."}[5m]))
/ sum(rate(skuel_http_requests_total[5m]))
```

### HTTP Latency Percentiles

```promql
# p50 latency (median)
histogram_quantile(0.50,
  rate(skuel_http_request_duration_seconds_bucket[5m])
)

# p95 latency
histogram_quantile(0.95,
  rate(skuel_http_request_duration_seconds_bucket[5m])
)

# p99 latency
histogram_quantile(0.99,
  rate(skuel_http_request_duration_seconds_bucket[5m])
)

# p95 latency by endpoint
histogram_quantile(0.95,
  sum by (endpoint, le) (
    rate(skuel_http_request_duration_seconds_bucket[5m])
  )
)
```

### HTTP Error Rates

```promql
# 5xx error rate (percentage)
100 * (sum(rate(skuel_http_requests_total{status=~"5.."}[5m])) or vector(0))
/ (sum(rate(skuel_http_requests_total[5m])) or vector(1))

# 4xx error rate (percentage)
100 * (sum(rate(skuel_http_requests_total{status=~"4.."}[5m])) or vector(0))
/ (sum(rate(skuel_http_requests_total[5m])) or vector(1))

# Error rate by endpoint
sum by (endpoint) (rate(skuel_http_errors_total[5m]))

# Top 5 endpoints by error count
topk(5, sum by (endpoint) (rate(skuel_http_errors_total[5m])))
```

### HTTP Performance Analysis

```promql
# Top 5 slowest endpoints (p95)
topk(5,
  histogram_quantile(0.95,
    sum by (endpoint, le) (
      rate(skuel_http_request_duration_seconds_bucket[5m])
    )
  )
)

# Request volume by endpoint (descending)
topk(10, sum by (endpoint) (rate(skuel_http_requests_total[5m])))

# Endpoints with latency > 1s (p95)
histogram_quantile(0.95,
  sum by (endpoint, le) (
    rate(skuel_http_request_duration_seconds_bucket[5m])
  )
) > 1.0
```

---

## Database Metrics Queries

### Neo4j Query Performance

```promql
# Total Neo4j queries per second
rate(skuel_neo4j_queries_total[5m])

# Queries by operation type
sum by (operation) (rate(skuel_neo4j_queries_total[5m]))

# Queries by label (entity type)
sum by (label) (rate(skuel_neo4j_queries_total[5m]))

# Query duration p95 by operation
histogram_quantile(0.95,
  sum by (operation, le) (
    rate(skuel_neo4j_query_duration_seconds_bucket[5m])
  )
)
```

### Neo4j Error Tracking

```promql
# Database error rate
rate(skuel_neo4j_errors_total[5m])

# Errors by operation
sum by (operation) (rate(skuel_neo4j_errors_total[5m]))

# Query success rate
(sum(rate(skuel_neo4j_queries_total[5m])) - sum(rate(skuel_neo4j_errors_total[5m])))
/ sum(rate(skuel_neo4j_queries_total[5m]))
```

### Slow Query Detection

```promql
# Queries taking > 500ms (p95)
histogram_quantile(0.95,
  sum by (operation, label, le) (
    rate(skuel_neo4j_query_duration_seconds_bucket[5m])
  )
) > 0.5

# Average query duration by label
avg by (label) (
  rate(skuel_neo4j_query_duration_seconds_sum[5m])
  / rate(skuel_neo4j_query_duration_seconds_count[5m])
)
```

---

## Domain Activity Queries

### Entity Creation Tracking

```promql
# Total entities created per second
rate(skuel_entities_created_total[5m])

# Creation rate by entity type
sum by (entity_type) (rate(skuel_entities_created_total[5m]))

# User-specific creation rate
sum by (user_uid, entity_type) (
  rate(skuel_entities_created_total[5m])
)

# Top 5 most-created entity types
topk(5, sum by (entity_type) (rate(skuel_entities_created_total[5m])))
```

### Completion Metrics

```promql
# Completion rate by entity type
sum by (entity_type) (rate(skuel_entities_completed_total[5m]))

# Completion ratio (completed / created)
sum by (entity_type) (rate(skuel_entities_completed_total[5m]))
/ sum by (entity_type) (rate(skuel_entities_created_total[5m]))

# Task completion rate (tasks only)
sum(rate(skuel_entities_completed_total{entity_type="task"}[5m]))
```

### Active Entity Tracking

```promql
# Current active entities by type
skuel_active_entities_count

# Total active entities across all types
sum(skuel_active_entities_count)

# Active entities per user
sum by (user_uid) (skuel_active_entities_count)
```

---

## Event Bus Queries

### Event Publication Metrics

```promql
# Event publication rate
rate(skuel_events_published_total[5m])

# Publications by event type
sum by (event_type) (rate(skuel_events_published_total[5m]))

# Top 5 most-published events
topk(5, sum by (event_type) (rate(skuel_events_published_total[5m])))

# Event publication overhead (p95)
histogram_quantile(0.95,
  rate(skuel_event_publish_duration_seconds_bucket[5m])
)
```

### Event Handler Performance

```promql
# Handler calls per second
rate(skuel_event_handler_calls_total[5m])

# Handler duration p95
histogram_quantile(0.95,
  sum by (handler, le) (
    rate(skuel_event_handler_duration_seconds_bucket[5m])
  )
)

# Slow handlers (>500ms p95)
histogram_quantile(0.95,
  sum by (handler, event_type, le) (
    rate(skuel_event_handler_duration_seconds_bucket[5m])
  )
) > 0.5

# Top 5 slowest handlers
topk(5,
  histogram_quantile(0.95,
    sum by (handler, le) (
      rate(skuel_event_handler_duration_seconds_bucket[5m])
    )
  )
)
```

### Event Handler Errors

```promql
# Handler error rate
rate(skuel_event_handler_errors_total[5m])

# Errors by handler
sum by (handler) (rate(skuel_event_handler_errors_total[5m]))

# Handler success rate
(sum(rate(skuel_event_handler_calls_total[5m])) - sum(rate(skuel_event_handler_errors_total[5m])))
/ sum(rate(skuel_event_handler_calls_total[5m]))
```

### Context Invalidations

```promql
# Invalidation rate
rate(skuel_context_invalidations_total[5m])

# Invalidations per user
sum by (user_uid) (rate(skuel_context_invalidations_total[5m]))

# Detect invalidation spikes (>10/sec)
rate(skuel_context_invalidations_total[5m]) > 10
```

---

## Graph Health Queries

### Graph Connectivity

```promql
# Graph density (avg relationships per entity)
skuel_graph_density

# Total entities
skuel_total_entities

# Total relationships
skuel_total_relationships

# Relationship-to-entity ratio
skuel_total_relationships / skuel_total_entities
```

### Orphaned Entity Detection

```promql
# Orphaned entities count
skuel_orphaned_entities_count

# Orphan percentage
100 * skuel_orphaned_entities_count / skuel_total_entities

# Alert on orphans (target: 0)
skuel_orphaned_entities_count > 0
```

### Relationship Layer Analysis

```promql
# Relationships by layer
skuel_relationships_count

# Breakdown by layer type
sum by (layer) (skuel_relationships_count)

# Lateral relationships by category
sum by (category) (skuel_lateral_relationships_by_category)

# Cross-domain connections heatmap
sum by (from_domain, to_domain) (skuel_cross_domain_relationships_count)
```

### Dependency Patterns

```promql
# Active BLOCKS relationships
skuel_blocking_relationships_count

# Active ENABLES relationships
skuel_enables_relationships_count

# Dependency chain length
skuel_dependency_chain_max_length

# Alert on deep chains (>5 levels)
skuel_dependency_chain_max_length > 5
```

---

## Search Performance Queries

### Search Volume and Latency

```promql
# Total searches per second
rate(skuel_searches_total[5m])

# Searches by type
sum by (search_type) (rate(skuel_searches_total[5m]))

# Search duration p95
histogram_quantile(0.95,
  sum by (search_type, le) (
    rate(skuel_search_duration_seconds_bucket[5m])
  )
)

# Slow searches (>1s p95)
histogram_quantile(0.95,
  sum by (search_type, le) (
    rate(skuel_search_duration_seconds_bucket[5m])
  )
) > 1.0
```

### Search Quality Metrics

```promql
# Average similarity score
avg(rate(skuel_search_similarity_score_sum[5m])
  / rate(skuel_search_similarity_score_count[5m]))

# Similarity p50 (median relevance)
histogram_quantile(0.50,
  rate(skuel_search_similarity_score_bucket[5m])
)

# High-quality results (similarity > 0.8)
sum(rate(skuel_search_similarity_score_bucket{le="1.0"}[5m]))
- sum(rate(skuel_search_similarity_score_bucket{le="0.8"}[5m]))
```

---

## Query/Operation Metrics

### Operation Performance

```promql
# Operation calls per second
rate(skuel_operation_calls_total[5m])

# Top 10 most-called operations
topk(10, sum by (operation_name) (rate(skuel_operation_calls_total[5m])))

# Operation duration p95
histogram_quantile(0.95,
  sum by (operation_name, le) (
    rate(skuel_operation_duration_seconds_bucket[5m])
  )
)

# Slow operations (>100ms p95)
histogram_quantile(0.95,
  sum by (operation_name, le) (
    rate(skuel_operation_duration_seconds_bucket[5m])
  )
) > 0.1
```

### Operation Error Tracking

```promql
# Operation error rate
rate(skuel_operation_errors_total[5m])

# Errors by operation
sum by (operation_name) (rate(skuel_operation_errors_total[5m]))

# Operation success rate
(sum by (operation_name) (rate(skuel_operation_calls_total[5m]))
 - sum by (operation_name) (rate(skuel_operation_errors_total[5m])))
/ sum by (operation_name) (rate(skuel_operation_calls_total[5m]))
```

---

## Aggregation Patterns

### Time Window Aggregation

```promql
# 5-minute rate (most common)
rate(skuel_http_requests_total[5m])

# 1-minute rate (more responsive)
rate(skuel_http_requests_total[1m])

# 15-minute rate (smoother)
rate(skuel_http_requests_total[15m])

# 1-hour average
avg_over_time(skuel_graph_density[1h])
```

### User Aggregation

```promql
# Per-user entity creation
sum by (user_uid) (rate(skuel_entities_created_total[5m]))

# Per-user graph density
skuel_graph_density{user_uid="user_mike"}

# All users combined
sum(skuel_total_entities)
```

### Multi-Dimensional Aggregation

```promql
# By entity type and user
sum by (entity_type, user_uid) (rate(skuel_entities_created_total[5m]))

# By endpoint and status
sum by (endpoint, status) (rate(skuel_http_requests_total[5m]))

# By event type and handler
sum by (event_type, handler) (rate(skuel_event_handler_calls_total[5m]))
```

---

## Common Pitfalls

### Don't Use rate() on Gauges

```promql
# WRONG - rate() is for counters only
rate(skuel_graph_density[5m])

# CORRECT - use gauges directly or with delta()
skuel_graph_density
delta(skuel_graph_density[5m])
```

### Avoid High Cardinality Labels

```promql
# WRONG - creates too many time series
sum by (user_uid, endpoint, method, status) (...)

# CORRECT - aggregate early
sum by (endpoint) (rate(skuel_http_requests_total[5m]))
```

### Handle Missing Data with or vector()

```promql
# WRONG - division by zero when no requests
sum(rate(skuel_http_errors_total[5m]))
/ sum(rate(skuel_http_requests_total[5m]))

# CORRECT - provide default value
(sum(rate(skuel_http_errors_total[5m])) or vector(0))
/ (sum(rate(skuel_http_requests_total[5m])) or vector(1))
```

### Label Matchers Use Regex

```promql
# Match 5xx status codes
status=~"5.."

# Match 4xx and 5xx
status=~"[45].."

# Exclude specific endpoint
endpoint!="/metrics"

# Match multiple values
entity_type=~"task|goal|habit"
```

---

## Query Optimization Tips

### Use Recording Rules for Complex Queries

If a query appears in multiple dashboards, create a recording rule:

```yaml
# prometheus.yml
groups:
  - name: skuel_aggregations
    interval: 30s
    rules:
      - record: skuel:http_requests:rate5m
        expr: rate(skuel_http_requests_total[5m])

      - record: skuel:http_latency:p95
        expr: histogram_quantile(0.95, rate(skuel_http_request_duration_seconds_bucket[5m]))
```

Then query the recording rule:
```promql
skuel:http_requests:rate5m
```

### Limit Time Series with topk/bottomk

```promql
# Instead of all endpoints
sum by (endpoint) (rate(skuel_http_requests_total[5m]))

# Get top 10 only
topk(10, sum by (endpoint) (rate(skuel_http_requests_total[5m])))
```

### Use Subqueries Sparingly

Subqueries are powerful but expensive:

```promql
# Expensive - subquery
max_over_time(
  rate(skuel_http_requests_total[5m])[1h:5m]
)

# Better - use dashboard time range filtering
```

---

## See Also

- [SKILL.md](SKILL.md) - Complete observability stack guide
- [INSTRUMENTATION.md](INSTRUMENTATION.md) - How to add metrics
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Debugging metrics issues
- [Prometheus Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/) - Official docs
