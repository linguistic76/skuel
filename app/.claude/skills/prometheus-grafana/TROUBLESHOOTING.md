# Troubleshooting Guide

> Common issues and debugging steps for SKUEL's observability stack

This guide covers the most common problems with Prometheus metrics and Grafana dashboards.

## Metrics Not Appearing in Prometheus

### Symptom

`/metrics` endpoint returns data, but Prometheus shows "no data" for queries.

### Diagnosis Steps

```bash
# 1. Verify metrics endpoint returns data
curl http://localhost:5001/metrics | grep skuel_http_requests_total

# Expected: Should see metric with labels
# skuel_http_requests_total{endpoint="/tasks",method="GET",status="200"} 42.0

# 2. Check Prometheus targets status
open http://localhost:9090/targets

# Expected: "skuel-app" target should be UP (green)
# If DOWN (red), see "Prometheus Cannot Scrape /metrics" section below

# 3. Check Prometheus scrape config
cat monitoring/prometheus/prometheus.yml

# Verify target address matches your app
# Expected:
#   - targets: ['host.docker.internal:5001']  # or actual IP

# 4. Test PromQL query in Prometheus UI
open http://localhost:9090/graph

# Run query: skuel_http_requests_total
# Expected: Time series with recent data
```

### Common Causes

#### Cause 1: Wrong Target Address

**Problem**: Prometheus scrape config points to wrong host/port

**Solution**:
```yaml
# monitoring/prometheus/prometheus.yml

scrape_configs:
  - job_name: 'skuel-app'
    static_configs:
      # Use host.docker.internal for Docker on Mac/Windows
      - targets: ['host.docker.internal:5001']

      # Or use actual IP address
      # - targets: ['192.168.1.100:5001']

      # NOT localhost (Docker container can't reach host's localhost)
      # - targets: ['localhost:5001']  # ❌ WRONG
```

After changing, restart Prometheus:
```bash
docker-compose restart prometheus
```

#### Cause 2: Firewall Blocking Port

**Problem**: Firewall blocks Prometheus from accessing port 5001

**Solution** (Linux):
```bash
# Allow port 5001
sudo ufw allow 5001/tcp

# Or disable firewall temporarily for testing
sudo ufw disable
```

**Solution** (macOS):
```bash
# Check if firewall is blocking
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate

# Add exception (if needed)
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /path/to/python
```

#### Cause 3: Scrape Timeout

**Problem**: `/metrics` endpoint takes too long to respond (>10s default)

**Solution**: Increase `scrape_timeout` in `prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'skuel-app'
    scrape_interval: 15s
    scrape_timeout: 30s  # Increase from default 10s
    static_configs:
      - targets: ['host.docker.internal:5001']
```

Check endpoint performance:
```bash
time curl http://localhost:5001/metrics
# Should complete in < 5 seconds
```

---

## Prometheus Cannot Scrape /metrics

### Symptom

Prometheus targets page shows "skuel-app" as DOWN with error message.

### Error: "Connection Refused"

**Diagnosis**:
```bash
# From Docker container, can you reach the app?
docker exec -it skuel-prometheus-1 wget -O- http://host.docker.internal:5001/metrics
```

**Solutions**:

1. **App not running**: Start the SKUEL app
   ```bash
   uv run python main.py
   ```

2. **Wrong port**: Check app is running on port 5001
   ```bash
   lsof -i :5001
   # Should show Python process
   ```

3. **Docker network issue**: Use host IP instead of `host.docker.internal`
   ```bash
   # Get your host IP
   ifconfig | grep "inet "

   # Update prometheus.yml
   - targets: ['192.168.1.100:5001']  # Your actual IP
   ```

### Error: "Context Deadline Exceeded"

**Diagnosis**: Prometheus scrape times out

**Solution**: `/metrics` endpoint is too slow

```bash
# Profile endpoint
time curl http://localhost:5001/metrics

# If > 10 seconds, investigate slow metrics
# Check for expensive gauge calculations
```

Optimize slow metrics:
- Move expensive queries to background tasks
- Use caching for gauges that don't change frequently
- Reduce label cardinality

---

## Dashboard Shows "No Data"

### Symptom

Grafana dashboard panels show "No data" despite metrics being in Prometheus.

### Diagnosis Steps

```bash
# 1. Verify metric exists in Prometheus
open http://localhost:9090/graph

# Run the exact query from Grafana panel
rate(skuel_http_requests_total[5m])

# If Prometheus shows data but Grafana doesn't, issue is with Grafana config
```

### Common Causes

#### Cause 1: Datasource Not Configured

**Solution**: Add Prometheus datasource in Grafana

1. Open Grafana: http://localhost:3000
2. Go to Configuration → Data Sources
3. Add Prometheus datasource:
   - URL: `http://prometheus:9090` (Docker internal network)
   - Access: Server (default)
4. Click "Save & Test" - should show "Data source is working"

#### Cause 2: Wrong Time Range

**Solution**: Adjust dashboard time range

1. Top-right corner of dashboard → Time range picker
2. Select "Last 5 minutes" or "Last 15 minutes"
3. If still no data, try "Last 6 hours" (Prometheus may have just started)

**Why**: Metrics only exist AFTER they're first tracked. If you just started the app, only recent data exists.

#### Cause 3: Query Syntax Error

**Solution**: Fix PromQL query

Common mistakes:
```promql
# WRONG - missing rate()
skuel_http_requests_total

# CORRECT - counters need rate() or increase()
rate(skuel_http_requests_total[5m])

# WRONG - rate() on gauge
rate(skuel_graph_density[5m])

# CORRECT - gauges used directly
skuel_graph_density
```

**See**: [PROMQL_PATTERNS.md](PROMQL_PATTERNS.md) for correct query patterns

#### Cause 4: Label Mismatch

**Solution**: Check labels match actual metrics

```promql
# WRONG - label doesn't exist
skuel_http_requests_total{route="/tasks"}

# CORRECT - label is "endpoint" not "route"
skuel_http_requests_total{endpoint="/tasks"}
```

Verify labels in Prometheus:
```promql
# See all labels for a metric
skuel_http_requests_total
```

---

## Dashboard Not Updating

### Symptom

Dashboard shows old data, doesn't refresh even when new metrics exist.

### Solutions

1. **Check refresh interval**:
   - Top-right → Refresh dropdown
   - Select "5s" or "10s" for real-time updates

2. **Check time range is "now"**:
   - Ensure time range includes "now"
   - Select "Last 5 minutes" instead of fixed time range

3. **Force refresh**:
   - Top-right → Refresh button (circular arrow)
   - Or press Ctrl+R / Cmd+R

4. **Check browser cache**:
   - Hard refresh: Ctrl+Shift+R / Cmd+Shift+R
   - Or open in incognito/private window

---

## High Cardinality Warnings

### Symptom

Prometheus logs show warnings about high cardinality:
```
level=warn msg="many samples rejected" reason="too many series"
```

### Diagnosis

```promql
# Check total time series count
prometheus_tsdb_symbol_table_size_bytes

# Count series for a specific metric
count(skuel_http_requests_total)

# If > 10,000 for one metric, you have high cardinality
```

### Solution: Reduce Label Cardinality

**Problem**: Unbounded label values

```python
# BAD - creates series for every unique path
prometheus_metrics.http.requests_total.labels(
    endpoint=request.full_path,  # e.g., "/tasks?id=123&page=5"
    session_id=session_id,       # Unique per session
)
```

**Solution**: Use bounded label sets

```python
# GOOD - fixed set of endpoints
prometheus_metrics.http.requests_total.labels(
    endpoint="/api/tasks",  # Normalize to route pattern
    method="GET",           # Only 5-6 HTTP methods
    status=200,             # Only ~15 status codes
)
```

**Rule**: Keep total series per metric < 1,000
- Total series = label1_values × label2_values × ... × labelN_values
- Example: 50 endpoints × 6 methods × 15 statuses = 4,500 series ✓

---

## Missing Data Points

### Symptom

Gaps in time series data on dashboards.

### Common Causes

#### Cause 1: Scrape Interval vs Retention

**Problem**: Querying data older than retention period

```yaml
# prometheus.yml
global:
  retention.time: 15d  # Prometheus only keeps 15 days
```

**Solution**: Increase retention or export to long-term storage

```yaml
# Increase retention to 30 days
command:
  - '--retention.time=30d'
  - '--storage.tsdb.path=/prometheus'
```

#### Cause 2: App Downtime

**Problem**: App was down, no metrics scraped during downtime

**Diagnosis**:
```promql
# Check scrape success
up{job="skuel-app"}

# If 0, scrape failed
# If 1, scrape succeeded
```

**Solution**: This is expected - gaps = downtime. No fix needed.

#### Cause 3: Metric Not Tracked

**Problem**: Code path not executed yet

```python
# If this never runs, metric won't exist
if rare_condition:
    prometheus_metrics.domains.entities_created.labels(...).inc()
```

**Solution**: Initialize metrics at startup with 0 value

```python
# In bootstrap
prometheus_metrics.domains.entities_created.labels(
    entity_type="task",
    user_uid="user_mike"
).inc(0)  # Initialize to 0
```

---

## Slow Queries in Grafana

### Symptom

Dashboard takes >10 seconds to load, panels timeout.

### Diagnosis

Check query complexity in Prometheus UI:
```bash
open http://localhost:9090/graph
# Run query from slow panel
# Note execution time at bottom
```

### Solutions

#### Solution 1: Reduce Time Range

```promql
# Instead of querying 30 days
rate(skuel_http_requests_total[30d])

# Query smaller window
rate(skuel_http_requests_total[5m])
```

#### Solution 2: Use Recording Rules

Create pre-computed aggregations:

```yaml
# monitoring/prometheus/recording_rules.yml
groups:
  - name: skuel_aggregations
    interval: 30s
    rules:
      - record: skuel:http_requests:rate5m
        expr: rate(skuel_http_requests_total[5m])

      - record: skuel:http_latency:p95
        expr: histogram_quantile(0.95, rate(skuel_http_request_duration_seconds_bucket[5m]))
```

Update `prometheus.yml`:
```yaml
rule_files:
  - /etc/prometheus/recording_rules.yml
```

Query recording rules (much faster):
```promql
skuel:http_requests:rate5m
```

#### Solution 3: Limit Series with topk()

```promql
# Instead of all endpoints (slow)
sum by (endpoint) (rate(skuel_http_requests_total[5m]))

# Get top 10 only (faster)
topk(10, sum by (endpoint) (rate(skuel_http_requests_total[5m])))
```

---

## Metric Values Seem Wrong

### Counter Not Increasing

**Problem**: Counter value is 0 or constant

**Diagnosis**:
```python
# Check if code path executes
prometheus_metrics.domains.entities_created.labels(
    entity_type="task",
    user_uid=user_uid
).inc()

# Add logging
logger.info(f"Incrementing entities_created for {user_uid}")
```

**Common Causes**:
1. Code path never executed (add logs to verify)
2. Wrong labels (check label values match query)
3. `prometheus_metrics` is None (add guard: `if prometheus_metrics:`)

### Gauge Shows Stale Data

**Problem**: Gauge doesn't update in real-time

**Diagnosis**: Check how gauge is updated

```python
# If gauge is only set on events
prometheus_metrics.domains.active_entities_count.labels(...).set(count)

# But events don't fire frequently, gauge stays stale
```

**Solution**: Use background task for periodic updates

```python
# Update gauge every 5 minutes via scheduler
async def update_active_count():
    count = await backend.count_active(user_uid)
    prometheus_metrics.domains.active_entities_count.labels(
        entity_type="task",
        user_uid=user_uid
    ).set(count)
```

### Histogram Percentiles Look Wrong

**Problem**: p95 latency is always at bucket boundary (e.g., exactly 1.0s)

**Diagnosis**: Histogram buckets don't match value distribution

```python
# Current buckets
buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

# But most values are 1.5s - 3.0s (gap between 1.0 and 2.5)
```

**Solution**: Add buckets in the expected range

```python
# Better buckets for 1-3 second range
buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 5.0, 10.0)
```

**Rule**: Buckets should have higher resolution where most values fall.

---

## Grafana Dashboard Import Failed

### Symptom

Error when importing dashboard JSON: "Dashboard validation failed"

### Solutions

#### Solution 1: Check JSON Syntax

```bash
# Validate JSON
cat monitoring/grafana/dashboards/system_health.json | jq .

# If error, fix JSON syntax (missing commas, brackets, etc.)
```

#### Solution 2: Check Datasource UID

Dashboard JSON references datasource by UID:

```json
{
  "datasource": {
    "uid": "prometheus-uid-here"
  }
}
```

**Fix**: Update to use datasource name instead:

```json
{
  "datasource": {
    "type": "prometheus",
    "uid": "${DS_PROMETHEUS}"
  }
}
```

Or use Grafana provisioning (auto-loads dashboards):

```yaml
# monitoring/grafana/provisioning/dashboards/dashboards.yml
apiVersion: 1
providers:
  - name: 'SKUEL Dashboards'
    folder: 'SKUEL'
    type: file
    options:
      path: /etc/grafana/provisioning/dashboards
```

---

## Prometheus Container Fails to Start

### Symptom

```bash
docker-compose up -d prometheus
# Error: Container exits immediately
```

### Diagnosis

```bash
# Check container logs
docker logs skuel-prometheus-1

# Common errors:
# - "config file error"
# - "permission denied"
# - "port already in use"
```

### Solutions

#### Error: "Opening storage failed"

**Cause**: Prometheus data directory has wrong permissions

**Solution**:
```bash
# Fix permissions
sudo chown -R 65534:65534 monitoring/prometheus/data

# Or use Docker volume
# In docker-compose.yml:
volumes:
  - prometheus_data:/prometheus

volumes:
  prometheus_data:
```

#### Error: "Bind for 0.0.0.0:9090 failed: port is already allocated"

**Cause**: Another Prometheus instance running

**Solution**:
```bash
# Find process using port 9090
lsof -i :9090

# Kill other Prometheus
kill <PID>

# Or change port in docker-compose.yml
ports:
  - "9091:9090"  # Use 9091 instead
```

#### Error: "Config file is invalid"

**Cause**: Syntax error in `prometheus.yml`

**Solution**:
```bash
# Validate config
docker run --rm -v $(pwd)/monitoring/prometheus:/etc/prometheus \
  prom/prometheus:latest \
  promtool check config /etc/prometheus/prometheus.yml

# Fix reported errors
```

---

## Verification Checklist

After troubleshooting, verify everything works:

```bash
# 1. App is running
curl http://localhost:5001/health
# Expected: 200 OK

# 2. Metrics endpoint works
curl http://localhost:5001/metrics | head -n 20
# Expected: Prometheus-formatted metrics

# 3. Prometheus is scraping
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.job=="skuel-app")'
# Expected: "health": "up"

# 4. Metrics appear in Prometheus
curl 'http://localhost:9090/api/v1/query?query=skuel_http_requests_total' | jq .
# Expected: "status": "success", results with data

# 5. Grafana can query Prometheus
curl -u admin:admin 'http://localhost:3000/api/datasources/proxy/1/api/v1/query?query=up'
# Expected: "status": "success"

# 6. Dashboard loads
open http://localhost:3000/d/system-health
# Expected: Panels with data (not "No data")
```

---

## Getting Help

If issues persist after troubleshooting:

1. **Check SKUEL documentation**:
   - `/docs/observability/PROMETHEUS_METRICS.md` - Comprehensive reference
   - `/docs/decisions/ADR-036-prometheus-primary-cache-pattern.md` - Architecture

2. **Check Prometheus documentation**:
   - [Prometheus Troubleshooting](https://prometheus.io/docs/prometheus/latest/troubleshooting/)
   - [PromQL Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)

3. **Check Grafana documentation**:
   - [Grafana Troubleshooting](https://grafana.com/docs/grafana/latest/troubleshooting/)

4. **Enable debug logging**:
   ```python
   # In main.py
   import logging
   logging.getLogger("core.infrastructure.monitoring").setLevel(logging.DEBUG)
   ```

5. **Create minimal reproduction**:
   ```python
   # Test metrics in isolation
   from prometheus_client import Counter, generate_latest

   test_counter = Counter('test_metric', 'Test metric')
   test_counter.inc()

   print(generate_latest().decode('utf-8'))
   # Should show: test_metric 1.0
   ```

---

## See Also

- [SKILL.md](SKILL.md) - Complete observability stack guide
- [INSTRUMENTATION.md](INSTRUMENTATION.md) - How to add metrics
- [PROMQL_PATTERNS.md](PROMQL_PATTERNS.md) - Query examples
- `/core/infrastructure/monitoring/prometheus_metrics.py` - Metric definitions
