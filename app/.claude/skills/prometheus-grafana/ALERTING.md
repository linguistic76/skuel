# Prometheus Alerting Guide for SKUEL

> "Proactive failure detection - alerts fire before users notice problems"

This guide covers Prometheus alerting rules, severity levels, and runbook patterns for SKUEL's observability stack.

---

## Quick Start

### View Active Alerts

```bash
# Prometheus UI
open http://localhost:9090/alerts

# API (JSON)
curl http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.type == "alerting")'

# Check specific alert
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.labels.alertname == "HighErrorRate")'
```

### Test Alerts Locally

```bash
# Validate alert rules syntax
./scripts/validate_prometheus_config.sh

# Simulate high error rate (fire HighErrorRate alert)
for i in {1..100}; do curl http://localhost:5001/nonexistent; done

# Watch alert fire (wait 5 minutes for threshold)
watch -n 10 'curl -s http://localhost:9090/api/v1/alerts | jq ".data.alerts[] | select(.labels.alertname == \"HighErrorRate\")"'
```

---

## Alert Categories

SKUEL has **14 production alerts** across 5 categories:

### 1. HTTP / API Health (2 alerts)

| Alert | Severity | Threshold | Duration | Trigger Condition |
|-------|----------|-----------|----------|-------------------|
| **HighErrorRate** | critical | >5% | 5m | HTTP error rate exceeds 5% over 5 minutes |
| **SlowHttpRequests** | warning | >5s | 5m | p95 latency exceeds 5 seconds |

**Example PromQL**:
```promql
# HighErrorRate
(
  sum(rate(skuel_http_errors_total[5m]))
  /
  sum(rate(skuel_http_requests_total[5m]))
) > 0.05
```

**Runbook**:
- Check `/logs` for error patterns
- Verify Neo4j connection status
- Review recent deployments/migrations
- Check database query performance

---

### 2. Database Health (3 alerts)

| Alert | Severity | Threshold | Duration | Trigger Condition |
|-------|----------|-----------|----------|-------------------|
| **Neo4jDown** | critical | 0 (down) | 1m | Neo4j connection unavailable for 1+ minute |
| **SlowDatabaseQueries** | warning | >2s | 5m | p95 query latency exceeds 2 seconds |
| **HighDatabaseErrorRate** | warning | >10% | 5m | Database error rate exceeds 10% |

**Example PromQL**:
```promql
# Neo4jDown (simple gauge check)
skuel_neo4j_connected == 0

# SlowDatabaseQueries (histogram quantile)
histogram_quantile(0.95,
  rate(skuel_neo4j_query_duration_seconds_bucket[5m])
) > 2.0
```

**Runbook**:
- **Neo4jDown**: Check Neo4j service status, verify network connectivity, check credentials
- **SlowDatabaseQueries**: Review slow queries in Neo4j Browser, check indexes, review APOC usage
- **HighDatabaseErrorRate**: Check Neo4j logs, verify schema constraints, review recent migrations

---

### 3. Event Processing (2 alerts)

| Alert | Severity | Threshold | Duration | Trigger Condition |
|-------|----------|-----------|----------|-------------------|
| **HighEventHandlerErrorRate** | warning | >10% | 5m | Event handler failures exceed 10% |
| **SlowEventHandlers** | warning | >5s | 5m | p95 handler latency exceeds 5 seconds |

**Example PromQL**:
```promql
# HighEventHandlerErrorRate
(
  sum(rate(skuel_event_handler_errors_total[5m]))
  /
  sum(rate(skuel_event_handler_calls_total[5m]))
) > 0.10
```

**Runbook**:
- Check event handler logs for exceptions
- Verify service dependencies (database, APIs)
- Review async patterns for blocking operations

---

### 4. Graph Health (2 alerts)

| Alert | Severity | Threshold | Duration | Trigger Condition |
|-------|----------|-----------|----------|-------------------|
| **HighOrphanedEntityCount** | warning | >100 | 10m | Entities with no relationships exceed 100 |
| **LongDependencyChains** | warning | >10 | 10m | BLOCKS→BLOCKED_BY chains exceed 10 levels |

**Example PromQL**:
```promql
# HighOrphanedEntityCount (simple gauge)
skuel_orphaned_entities_count > 100

# LongDependencyChains
skuel_dependency_chain_max_length > 10
```

**Runbook**:
- **HighOrphanedEntityCount**: Review entity creation logic, check relationship service
- **LongDependencyChains**: Review task/goal dependency structure, check for circular dependencies

---

### 5. AI Services (4 alerts) - Phase 1 (January 2026)

| Alert | Severity | Threshold | Duration | Trigger Condition |
|-------|----------|-----------|----------|-------------------|
| **HighAIErrorRate** | warning | >20% | 5m | AI API error rate exceeds 20% |
| **EmbeddingQueueBacklog** | warning | >500 | 15m | Embedding queue has >500 pending items |
| **HighEmbeddingFailureRate** | warning | >20% | 5m | Embedding generation failures exceed 20% |
| **SlowAICalls** | warning | >30s | 5m | p95 AI API latency exceeds 30 seconds |

**Example PromQL**:
```promql
# HighAIErrorRate
(
  sum(rate(skuel_ai_errors_total[5m]))
  /
  sum(rate(skuel_ai_requests_total[5m]))
) > 0.20

# EmbeddingQueueBacklog (simple gauge)
skuel_embedding_queue_size > 500
```

**Runbook**:
- **HighAIErrorRate**: Check API keys (HF_API_TOKEN, OPENAI_API_KEY), verify rate limits, check provider status pages
- **EmbeddingQueueBacklog**: Check worker logs, verify HuggingFace API availability, consider increasing batch size
- **HighEmbeddingFailureRate**: Check OpenAI status, review error logs, verify text preprocessing
- **SlowOpenAICalls**: Check OpenAI service status, review batch sizes, verify network latency

---

## Alert Severity Levels

SKUEL uses 2 severity levels:

| Severity | Definition | Response Time | Examples |
|----------|------------|---------------|----------|
| **critical** | Service down or severely degraded | Immediate (PagerDuty) | Neo4jDown, HighErrorRate |
| **warning** | Degraded performance or approaching limits | Within 1 hour | SlowHttpRequests, EmbeddingQueueBacklog |

**Severity Guidelines**:
- Use **critical** for: Service unavailability, data loss risk, security breaches
- Use **warning** for: Performance degradation, queue backlogs, approaching resource limits

---

## Adding New Alerts

### 1. Choose Alert Type

**Decision Tree**:
```
Is this a service availability issue? (e.g., database down)
├─ YES → Use Gauge with threshold (skuel_neo4j_connected == 0)
└─ NO  → Is this a rate/percentage metric?
    ├─ YES → Use Counter ratio (errors / total requests)
    └─ NO  → Is this a latency metric?
        ├─ YES → Use Histogram quantile (p95/p99)
        └─ NO  → Use Gauge with threshold (queue size, entity count)
```

### 2. Write the Alert Rule

Add to `/monitoring/prometheus/alerts.yml`:

```yaml
groups:
  - name: skuel_critical
    interval: 30s
    rules:
      - alert: YourAlertName
        expr: |
          # Your PromQL expression
          skuel_your_metric > threshold
        for: 5m  # Fire only after 5 minutes above threshold
        labels:
          severity: warning  # or critical
        annotations:
          summary: "Brief description (1 line)"
          description: "Detailed context with {{ $value }}"
          runbook: "Step-by-step resolution guide"
```

### 3. Validate the Rule

```bash
# Validate syntax
./scripts/validate_prometheus_config.sh

# Restart Prometheus to load new rule
docker compose restart prometheus

# Check rule loaded
curl http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.name == "YourAlertName")'
```

### 4. Test the Alert

```bash
# Trigger the condition (e.g., generate errors)
# Example: Simulate high error rate
for i in {1..100}; do curl http://localhost:5001/nonexistent; done

# Watch alert state change (inactive → pending → firing)
watch -n 10 'curl -s http://localhost:9090/api/v1/alerts | jq ".data.alerts[] | select(.labels.alertname == \"YourAlertName\")"'

# Alert states:
# - inactive: Condition not met
# - pending: Condition met, waiting for 'for' duration
# - firing: Alert active (ready to send notification)
```

---

## Alert Best Practices

### 1. Threshold Selection

**Guidelines**:
- Start conservative (high thresholds) → tune down based on real data
- Use percentiles (p95/p99) for latency, not averages (p50)
- Set `for` duration to avoid alert flapping (5-15 minutes typical)

**Example Thresholds**:
```yaml
# Too sensitive (fires on every blip)
for: 30s  # ❌ BAD

# Good balance (confirms sustained issue)
for: 5m   # ✅ GOOD

# Too lenient (problem persists too long)
for: 30m  # ⚠️ Use only for non-critical alerts
```

### 2. Annotation Quality

**Good Annotations**:
```yaml
annotations:
  summary: "High HTTP error rate (>5%)"  # ✅ Specific, actionable
  description: "Error rate is {{ $value | humanizePercentage }} over last 5 minutes"  # ✅ Includes current value
  runbook: "1. Check /logs for patterns, 2. Verify Neo4j connection, 3. Review recent deploys"  # ✅ Step-by-step
```

**Bad Annotations**:
```yaml
annotations:
  summary: "Something is wrong"  # ❌ Vague
  description: "Errors detected"  # ❌ No context
  runbook: "Fix it"  # ❌ Not helpful
```

### 3. Label Cardinality

**Avoid high-cardinality labels in alerts**:

```yaml
# BAD: user_uid creates thousands of alerts
expr: skuel_active_entities_count{user_uid="user_123"} > 100  # ❌

# GOOD: Aggregate across all users
expr: sum(skuel_active_entities_count) > 10000  # ✅
```

---

## Alertmanager Integration (Optional)

Prometheus can route alerts to **Alertmanager** for notifications (email, Slack, PagerDuty).

### Setup Alertmanager

```yaml
# docker-compose.yml
services:
  alertmanager:
    image: prom/alertmanager:v0.26.0
    ports:
      - "9093:9093"
    volumes:
      - ./monitoring/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml
    networks:
      - skuel-network
```

### Configure Routing

```yaml
# monitoring/alertmanager/alertmanager.yml
global:
  slack_api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'

route:
  receiver: 'slack-critical'
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

  routes:
    - match:
        severity: critical
      receiver: 'pagerduty'
    - match:
        severity: warning
      receiver: 'slack-warnings'

receivers:
  - name: 'slack-critical'
    slack_configs:
      - channel: '#alerts-critical'
        title: 'SKUEL Alert: {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ end }}'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: YOUR_PAGERDUTY_KEY

  - name: 'slack-warnings'
    slack_configs:
      - channel: '#alerts-warnings'
```

### Update Prometheus Config

```yaml
# monitoring/prometheus/prometheus.yml
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
```

---

## Common Alert Patterns

### 1. Rate-Based Alerts (Error Rates)

```yaml
- alert: HighErrorRate
  expr: |
    (
      sum(rate(skuel_http_errors_total[5m]))
      /
      sum(rate(skuel_http_requests_total[5m]))
    ) > 0.05
  for: 5m
```

**Key Points**:
- Use `rate()` for counters (calculates per-second rate)
- Divide errors by total for percentage
- 5-minute window smooths out spikes

### 2. Latency-Based Alerts (p95/p99)

```yaml
- alert: SlowHttpRequests
  expr: |
    histogram_quantile(0.95,
      rate(skuel_http_request_duration_seconds_bucket[5m])
    ) > 5.0
  for: 5m
```

**Key Points**:
- Use `histogram_quantile()` for percentiles
- 0.95 = 95th percentile (5% of requests slower)
- Requires histogram metric (not summary)

### 3. Gauge-Based Alerts (Thresholds)

```yaml
- alert: HighOrphanedEntityCount
  expr: skuel_orphaned_entities_count > 100
  for: 10m
```

**Key Points**:
- Simple threshold on gauge metric
- No `rate()` needed (gauge is absolute value)
- Longer `for` duration (10m) avoids flapping

### 4. Absence Alerts (Service Down)

```yaml
- alert: Neo4jDown
  expr: skuel_neo4j_connected == 0
  for: 1m
```

**Key Points**:
- Gauge metric (1 = up, 0 = down)
- Short `for` duration (1m) for critical services
- Can also use `up == 0` for Prometheus targets

---

## Alert Runbook Template

When adding new alerts, use this runbook template:

```yaml
annotations:
  summary: "[One-line description of the problem]"
  description: "[Context with {{ $value }} and impact]"
  runbook: |
    1. **Identify**: [How to confirm the issue]
       - Check [logs/dashboard/metrics]
       - Look for [specific patterns]

    2. **Diagnose**: [Root cause analysis]
       - Common causes: [list 3-5 scenarios]
       - Check [dependencies/configs/recent changes]

    3. **Resolve**: [Step-by-step fix]
       - Short-term: [immediate mitigation]
       - Long-term: [permanent fix]

    4. **Verify**: [How to confirm resolution]
       - Check [metric returns to normal]
       - Monitor [related metrics]

    5. **Escalate**: [When to escalate and to whom]
       - If unresolved after [time], contact [team]
```

---

## Troubleshooting Alerts

### Alert Not Firing

```bash
# 1. Check rule is loaded
curl http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.name == "YourAlert")'

# 2. Check expression evaluates
curl -G http://localhost:9090/api/v1/query --data-urlencode 'query=skuel_your_metric > threshold'

# 3. Check data exists
curl http://localhost:5001/metrics | grep skuel_your_metric

# 4. Check Prometheus logs
docker logs skuel-prometheus | grep -i error
```

### Alert Flapping (Firing/Resolving Repeatedly)

**Causes**:
- `for` duration too short
- Threshold too close to normal values
- Metric is noisy/spiky

**Fix**:
```yaml
# Before (flapping)
for: 30s  # Too short
expr: metric > 10  # Too close to normal

# After (stable)
for: 5m  # Longer duration
expr: metric > 20  # Buffer zone
```

### Alert Not Resolving

**Check**:
- Is the underlying condition still true?
- Are metrics still being scraped?
- Is Prometheus evaluating rules?

```bash
# Check current metric value
curl http://localhost:5001/metrics | grep skuel_your_metric

# Check alert state
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.labels.alertname == "YourAlert")'
```

---

## Production Checklist

Before deploying alerts to production:

- [ ] Validated syntax with `promtool check rules`
- [ ] Tested alert fires in staging environment
- [ ] Confirmed `for` duration appropriate (5-15 minutes)
- [ ] Severity level matches impact (critical vs warning)
- [ ] Runbook includes step-by-step resolution
- [ ] Alert annotations include `{{ $value }}`
- [ ] Low cardinality labels (no user_uid, task_uid, etc.)
- [ ] Alertmanager routing configured (if using)
- [ ] Tested alert resolution (condition returns to normal)
- [ ] Documented in skill (ALERTING.md)

---

## Next Steps

1. **Review existing alerts**: `curl http://localhost:9090/api/v1/rules`
2. **Create Grafana alert dashboard**: Import panel showing active alerts
3. **Set up Alertmanager**: Configure Slack/PagerDuty notifications
4. **Define SLOs**: Create recording rules for service level objectives
5. **Alert tuning**: Monitor for false positives, adjust thresholds

**See Also**:
- `SKILL.md` - Complete metrics reference
- `INSTRUMENTATION.md` - How to add new metrics
- `PROMQL_PATTERNS.md` - Query patterns for dashboards
- `/monitoring/prometheus/alerts.yml` - Production alert rules
