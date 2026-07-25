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
for i in {1..100}; do curl http://localhost:8000/nonexistent; done

# Watch alert fire (wait 5 minutes for threshold)
watch -n 10 'curl -s http://localhost:9090/api/v1/alerts | jq ".data.alerts[] | select(.labels.alertname == \"HighErrorRate\")"'
```

---

## Where Alerts Actually Evaluate

Alert rules run wherever Prometheus runs — and **Prometheus runs only in the dev stack**
(`./dev up-monitoring`), scraping the dev app backed by **local Docker Neo4j**. The production
droplet runs no Prometheus (PR #803 posture: app + Caddy only, `/metrics` blocked publicly).

Consequence: the AuraDB cap alert rules do **not** observe AuraDB. The **production
evaluation posture** (ruled 2026-07-25) is a two-part answer:

1. **In-app evaluator** — the 5-min graph-health poller feeds each freshly polled count
   through `check_aura_cap_headroom()` (`core/infrastructure/monitoring/aura_cap_check.py`):
   WARNING above 80% of cap, ERROR above 95%, logged **every cycle** while over threshold so
   any log tail surfaces it. Thresholds live in `core/constants.py` `AuraDBCaps` and are
   drift-pinned to the alert exprs by `tests/unit/test_metric_reference_drift.py`. Grep:

   ```bash
   docker compose logs skuel-app | grep 'AuraDB cap'
   ```

2. **Weekly manual verification** — read the gauges when the Sunday telemetry-retention
   cron runs (same rhythm, see DO_MIGRATION_GUIDE § Operations Runbook):

   ```bash
   docker compose exec skuel-app curl -s localhost:5001/metrics \
     | grep -E 'skuel_total_(entities|relationships) '
   ```

A headless droplet Prometheus was considered and **deferred**: without Alertmanager (see
§ Alertmanager below) it would evaluate alerts nobody sees — its UI sits on a firewalled
port — while adding a resident TSDB to a small droplet. Revisit only under the Alertmanager
trigger (a production Prometheus with unattended alerting genuinely wanted).

**Timing caveat**: the poller runs its first pass at startup (poll-first loop), so the
gauges populate within seconds of boot. If a reading looks wrong right after a restart,
check `skuel_graph_health_poll_last_success_timestamp_seconds` — a value of ~boot time
that never advances means passes are failing and the gauges are frozen.

(`./dev knowledge-health` covers only the knowledge subgraph and `./dev telemetry-retention`
only prunable telemetry — neither reports total graph counts against the 200k/400k caps.)

---

## Alert Categories

SKUEL has **14 alerting rules** across 5 categories (plus one commented-out SLO rule,
`ErrorBudgetDepleted`, staged in `alerts.yml`):

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

### 2. Database Health (2 alerts)

| Alert | Severity | Threshold | Duration | Trigger Condition |
|-------|----------|-----------|----------|-------------------|
| **SlowDatabaseQueries** | warning | >2s | 5m | p95 query latency exceeds 2 seconds |
| **HighDatabaseErrorRate** | warning | >10% | 5m | Database error rate exceeds 10% |

**Example PromQL**:
```promql
# SlowDatabaseQueries (histogram quantile)
histogram_quantile(0.95,
  rate(skuel_neo4j_query_duration_seconds_bucket[5m])
) > 2.0
```

**Runbook**:
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

### 4. Graph Health (4 alerts)

| Alert | Severity | Threshold | Duration | Trigger Condition |
|-------|----------|-----------|----------|-------------------|
| **HighOrphanedEntityCount** | warning | >100 | 10m | Entities with no relationships exceed 100 |
| **AuraNodeCapApproaching** | critical | >160,000 | 10m | Graph exceeds 80% of AuraDB Free 200k node cap |
| **AuraRelationshipCapApproaching** | critical | >320,000 | 10m | Graph exceeds 80% of AuraDB Free 400k relationship cap |
| **GraphHealthPollerStale** | warning | >900s | 5m | Graph-health poller hasn't succeeded in 15 min (3 missed cycles) — the 16 relationship/knowledge gauges are frozen |

**Example PromQL**:
```promql
# HighOrphanedEntityCount (simple gauge)
skuel_orphaned_entities_count > 100

# AuraNodeCapApproaching — 80% of the AuraDB Free 200k node cap
skuel_total_entities > 160000
```

**AuraDB Free cap context**: 200k nodes / 400k relationships; writes start failing AT the cap,
so 80% is the act-now line. The gauges come from the 5-min graph-health poller
(`scripts/dev/bootstrap.py`). These rules evaluate only in dev — in production the same
counts are evaluated in-app every poll cycle (`check_aura_cap_headroom`: WARNING above 80%,
ERROR above 95%; thresholds in `AuraDBCaps`, drift-pinned to these exprs). See § Where
Alerts Actually Evaluate.

**Runbook**:
- **HighOrphanedEntityCount**: Review entity creation logic, check relationship service
- **AuraNodeCapApproaching / AuraRelationshipCapApproaching**: Run `./dev telemetry-retention`,
  review growth with `./dev knowledge-health`, consider the invite gate / paid tier
- **GraphHealthPollerStale**: Check app logs for graph-health errors
  (`docker logs skuel-app | grep -i 'graph health'`), verify Neo4j via `/health/ready`

---

### 5. AI Services (4 alerts)

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

# HighEmbeddingFailureRate — status="skipped" (content-hash idempotency, ADR-074 §8)
# is EXCLUDED from the denominator: force syncs/backfills produce large benign skip
# volumes that would dilute the real failure ratio exactly when it matters most.
(
  sum(rate(skuel_embeddings_processed_total{status="failed"}[5m]))
  /
  sum(rate(skuel_embeddings_processed_total{status=~"success|failed|dropped"}[5m]))
) > 0.20
```

**Runbook**:
- **HighAIErrorRate**: Check OPENAI_API_KEY (the wired provider for both chat and embeddings — ADR-068; the BGE/HF adapter is staged but not selectable), verify rate limits, check provider status pages
- **EmbeddingQueueBacklog**: Check worker logs, verify OpenAI API availability, consider increasing batch size
- **HighEmbeddingFailureRate**: Check OpenAI status, review error logs, verify text preprocessing
- **SlowAICalls**: Check provider status pages, review batch sizes, verify network latency

---

## Alert Severity Levels

SKUEL uses 2 severity levels:

| Severity | Definition | Response Time | Examples |
|----------|------------|---------------|----------|
| **critical** | Service down, data loss risk, or hard caps approaching | Immediate | HighErrorRate, AuraNodeCapApproaching |
| **warning** | Degraded performance or approaching limits | Within 1 hour | SlowHttpRequests, EmbeddingQueueBacklog |

**Severity Guidelines**:
- Use **critical** for: Service unavailability, data loss risk, security breaches
- Use **warning** for: Performance degradation, queue backlogs, approaching resource limits

---

## Adding New Alerts

### 1. Choose Alert Type

**Decision Tree**:
```
Is this a rate/percentage metric?
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
docker compose --profile monitoring restart prometheus

# Check rule loaded
curl http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.name == "YourAlertName")'
```

### 4. Test the Alert

```bash
# Trigger the condition (e.g., generate errors)
# Example: Simulate high error rate
for i in {1..100}; do curl http://localhost:8000/nonexistent; done

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
# BAD: per-endpoint alerts create one alert per route
expr: skuel_http_request_duration_seconds{endpoint="/api/tasks"} > 2.0  # ❌

# GOOD: aggregate across endpoints
expr: histogram_quantile(0.95, sum by (le) (rate(skuel_http_request_duration_seconds_bucket[5m]))) > 2.0  # ✅
```

---

## Alertmanager: Deliberately Not Adopted

SKUEL runs no Alertmanager. Single operator, no notification chain — firing alerts are read in
the Prometheus UI (`http://localhost:9090/alerts`) when the dev monitoring stack is up. The
`alerting:` block in `prometheus.yml` stays commented out. Revisit only if a production
Prometheus with unattended alerting is ever wanted (see § Where Alerts Actually Evaluate).

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
- alert: AppDown
  expr: up{job="skuel-app"} == 0
  for: 1m
```

**Key Points**:
- The Prometheus-injected `up` metric is 1 when scrape succeeds, 0 when it fails
- Short `for` duration (1m) for critical services
- Use `up == 0` rather than custom heartbeat gauges

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
curl http://localhost:8000/metrics | grep skuel_your_metric

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
curl http://localhost:8000/metrics | grep skuel_your_metric

# Check alert state
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.labels.alertname == "YourAlert")'
```

---

## Production Checklist

Before deploying alerts to production:

- [ ] Validated syntax with `./scripts/validate_prometheus_config.sh` (promtool)
- [ ] Tested alert fires locally (dev monitoring stack)
- [ ] Confirmed `for` duration appropriate (5-15 minutes)
- [ ] Severity level matches impact (critical vs warning)
- [ ] Runbook includes step-by-step resolution
- [ ] Alert annotations include `{{ $value }}`
- [ ] Low cardinality labels (no user_uid, task_uid, etc.)
- [ ] Tested alert resolution (condition returns to normal)
- [ ] Documented in skill (ALERTING.md)

---

## Next Steps

1. **Review existing alerts**: `curl http://localhost:9090/api/v1/rules`
2. **Alert tuning**: Monitor for false positives, adjust thresholds

Non-goals (deliberate): Alertmanager notification routing and SLO recording rules — the
`ErrorBudgetDepleted` rule stays commented out in `alerts.yml` unless SLOs are ever defined.

**See Also**:
- `SKILL.md` - Complete metrics reference
- `INSTRUMENTATION.md` - How to add new metrics
- `PROMQL_PATTERNS.md` - Query patterns for dashboards
- `/monitoring/prometheus/alerts.yml` - Production alert rules
