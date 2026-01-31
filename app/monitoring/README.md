# SKUEL Monitoring Infrastructure

Prometheus + Grafana observability stack for SKUEL.

## Quick Start

### 1. Start Services

```bash
# From /home/mike/skuel/app
docker compose up -d prometheus grafana

# Check status
docker compose ps
```

### 2. Verify Endpoints

- **Prometheus UI**: http://localhost:9090
- **Grafana UI**: http://localhost:3000 (admin/admin)
- **SKUEL Metrics**: http://localhost:5001/metrics

### 3. Verify Prometheus Scraping

1. Open Prometheus UI: http://localhost:9090
2. Go to Status → Targets
3. Verify `skuel-app` target shows **UP** (green)

If target shows DOWN:
- Ensure SKUEL app is running: `poetry run python main.py`
- Check docker network: `docker network inspect skuel_skuel-network`
- Verify metrics endpoint: `curl http://localhost:5001/metrics`

### 4. Verify Grafana Datasource

1. Open Grafana: http://localhost:3000
2. Login with admin/admin (change password if prompted)
3. Go to Connections → Data sources
4. Verify "Prometheus" datasource exists and is working

## Architecture

### Phase 1: Foundation (Implemented ✅)

**Goal**: Get Prometheus + Grafana running, /metrics endpoint working

**Components**:
- `/metrics` endpoint - Prometheus scrape target
- Prometheus server - Metrics collection
- Grafana - Visualization
- PrometheusMetrics class - Metric definitions

**Metrics Available** (from prometheus-client defaults):
- Python runtime metrics (GC, memory, CPU)
- Process metrics (virtual memory, resident memory, CPU time)

**Custom Metrics Defined** (Phase 2+ will populate these):
```python
# System Health
skuel_cpu_usage_percent
skuel_memory_usage_bytes
skuel_neo4j_connected

# HTTP Traffic
skuel_http_requests_total{method, endpoint, status}
skuel_http_request_duration_seconds{method, endpoint}
skuel_http_errors_total{method, endpoint, status}

# Database Operations
skuel_neo4j_queries_total{operation, label}
skuel_neo4j_query_duration_seconds{operation, label}
skuel_neo4j_errors_total{operation}

# Event Bus
skuel_events_published_total{event_type}
skuel_event_handler_duration_seconds{event_type, handler}
skuel_event_handler_errors_total{event_type, handler}

# Domain Activity
skuel_entities_created_total{entity_type, user_uid}
skuel_entities_completed_total{entity_type, user_uid}
skuel_active_entities_count{entity_type, user_uid}

# Graph Health (Phase 4 PRIMARY GOAL)
skuel_relationships_count{layer, user_uid}
skuel_lateral_relationships_by_category{category, user_uid}
skuel_graph_density{user_uid}
skuel_blocking_relationships_count{user_uid}
skuel_orphaned_entities_count{user_uid}

# Search Quality
skuel_searches_total{search_type}
skuel_search_duration_seconds{search_type}
skuel_search_similarity_score{search_type}
```

## Configuration Files

### Prometheus

**File**: `/monitoring/prometheus/prometheus.yml`

```yaml
scrape_configs:
  - job_name: 'skuel-app'
    static_configs:
      - targets: ['skuel-app:5001']  # Docker service name
    scrape_interval: 15s
```

**Retention**: 7 days (development)

### Grafana

**Datasource**: `/monitoring/grafana/provisioning/datasources/prometheus.yml`
- Auto-configures Prometheus datasource on startup
- No manual setup needed

**Dashboards**: `/monitoring/grafana/provisioning/dashboards/skuel.yml`
- Auto-loads dashboards from `/monitoring/grafana/dashboards/`
- Dashboards are version-controlled (JSON files)

## Development Workflow

### Testing Metrics Endpoint

```bash
# Quick test
poetry run python scripts/test_metrics_endpoint.py

# Manual curl
curl http://localhost:5001/metrics

# Expected output:
# HELP python_gc_objects_collected_total Objects collected during gc
# TYPE python_gc_objects_collected_total counter
# python_gc_objects_collected_total{generation="0"} 249.0
# ...
```

### Querying Metrics in Prometheus

1. Open Prometheus UI: http://localhost:9090
2. Go to Graph tab
3. Try queries:
   ```promql
   # Python runtime info
   python_info

   # Process memory usage
   process_resident_memory_bytes

   # Custom metrics (Phase 2+)
   skuel_http_requests_total
   rate(skuel_http_requests_total[5m])
   ```

### Creating Dashboards in Grafana

1. Open Grafana: http://localhost:3000
2. Create → Dashboard → Add visualization
3. Select "Prometheus" datasource
4. Write PromQL query
5. Configure visualization
6. Save dashboard

**Export for version control**:
```bash
# Get dashboard UID from URL: /d/{uid}/...
curl -H "Authorization: Bearer {api_key}" \
  http://localhost:3000/api/dashboards/uid/{uid} | jq .dashboard > dashboards/{name}.json

# Commit to git
git add monitoring/grafana/dashboards/{name}.json
git commit -m "Add {name} dashboard"
```

## Troubleshooting

### Prometheus target DOWN

**Symptom**: Prometheus UI shows skuel-app target as DOWN (red)

**Causes & Fixes**:

1. **SKUEL app not running**
   ```bash
   poetry run python main.py
   ```

2. **Docker network mismatch**
   ```bash
   # Check if services are on same network
   docker network inspect skuel_skuel-network
   # Should show both skuel-app and prometheus containers
   ```

3. **Wrong port in prometheus.yml**
   - Verify SKUEL app port: `docker compose ps skuel-app`
   - Update prometheus.yml if needed
   - Restart Prometheus: `docker compose restart prometheus`

4. **Firewall blocking**
   ```bash
   # Test connection from Prometheus container
   docker exec skuel-prometheus wget -O- http://skuel-app:5001/metrics
   ```

### Grafana datasource connection failed

**Symptom**: Grafana shows "Error reading Prometheus" or datasource health check fails

**Causes & Fixes**:

1. **Prometheus not running**
   ```bash
   docker compose ps prometheus
   docker compose logs prometheus
   ```

2. **Wrong Prometheus URL in datasource**
   - Should be: `http://prometheus:9090` (Docker service name)
   - NOT: `http://localhost:9090` (that's host machine, not container)

3. **Network issues**
   ```bash
   # Test from Grafana container
   docker exec skuel-grafana wget -O- http://prometheus:9090/-/healthy
   ```

### No custom metrics showing

**Expected in Phase 1**: Only Python/process metrics will show. Custom SKUEL metrics (skuel_*) are defined but not yet populated.

**Phase 2+ will populate these metrics** by instrumenting:
- HTTP middleware (Phase 2)
- UniversalNeo4jBackend (Phase 2)
- Event bus (Phase 3)
- Domain services (Phase 3)
- Relationship tracking (Phase 4)

## Next Steps

See `/docs/observability/PROMETHEUS_METRICS.md` (to be created in Phase 5) for:
- Complete metrics reference
- Dashboard usage guide
- Query examples
- Alert rules (future)

See implementation plan at plan file for:
- Phase 2: HTTP & Database Instrumentation
- Phase 3: Event Bus & Domain Metrics
- Phase 4: Graph Health & Lateral Relationships (PRIMARY GOAL)
- Phase 5: Search Quality & Polish
