# Prometheus Restart & Alert Testing Results

**Date**: 2026-01-31
**Test Status**: ✅ PASSED (Configuration & Alerts)
**Pending**: Metrics verification (requires app running)

---

## Test Execution Summary

### ✅ Phase 1: Container Restart
- **Action**: Restarted Prometheus container
- **Issue Found**: Volume mount not applied (restart doesn't recreate container)
- **Resolution**: Ran `docker compose up -d prometheus` to recreate container
- **Result**: ✅ Container recreated with new volume mounts

### ✅ Phase 2: Configuration Verification
- **prometheus.yml**: ✅ Loaded successfully
- **alerts.yml**: ✅ Mounted at `/etc/prometheus/alerts.yml`
- **rule_files directive**: ✅ Correctly references alerts file
- **Prometheus API**: ✅ Responding on port 9090

### ✅ Phase 3: Alert Rules Verification
- **Total alerts loaded**: 13/13 ✅
- **Alert group**: `skuel_critical` ✅
- **Source file**: `/etc/prometheus/alerts.yml` ✅
- **All alerts health**: OK ✅
- **Evaluation times**: <1ms (excellent performance) ✅

---

## Alert Inventory

### 🔴 Critical Alerts (2)

| Alert | Threshold | Duration | Status |
|-------|-----------|----------|--------|
| HighErrorRate | >5% HTTP errors | 5m | ✅ Loaded, inactive |
| Neo4jDown | Database unavailable | 1m | ✅ Loaded, inactive |

### 🟡 Warning Alerts (11)

| Alert | Threshold | Duration | Status |
|-------|-----------|----------|--------|
| SlowHttpRequests | p95 >5s | 5m | ✅ Loaded, inactive |
| SlowDatabaseQueries | p95 >2s | 5m | ✅ Loaded, inactive |
| HighDatabaseErrorRate | >10% errors | 5m | ✅ Loaded, inactive |
| HighEventHandlerErrorRate | >10% failures | 5m | ✅ Loaded, inactive |
| SlowEventHandlers | p95 >5s | 5m | ✅ Loaded, inactive |
| HighOrphanedEntityCount | >100 entities | 10m | ✅ Loaded, inactive |
| LongDependencyChains | >10 levels | 10m | ✅ Loaded, inactive |
| **HighOpenAIErrorRate** | >20% failures | 5m | ✅ Loaded, inactive |
| **EmbeddingQueueBacklog** | >500 items | 15m | ✅ Loaded, inactive |
| **HighEmbeddingFailureRate** | >20% failures | 5m | ✅ Loaded, inactive |
| **SlowOpenAICalls** | p95 >30s | 5m | ✅ Loaded, inactive |

**Note**: Bold alerts are new AI/LLM metrics (Phase 1)

---

## Alert States Explanation

All alerts currently show **"inactive"** state because:
1. SKUEL app is not running (no metrics being generated)
2. This is the expected state when no data is available
3. Once app starts and metrics flow, alerts will evaluate properly

**Alert State Progression**:
```
inactive → pending → firing
   ↑          ↑         ↑
   No data    Condition  Alert for
   available  met        'for' duration
```

---

## Pending Verification (Requires SKUEL App)

The following tests require the SKUEL app to be running:

### ⏸️ Metrics Exposure
- [ ] OpenAI request metrics (`skuel_openai_requests_total`)
- [ ] OpenAI duration metrics (`skuel_openai_duration_seconds`)
- [ ] OpenAI token metrics (`skuel_openai_tokens_total`)
- [ ] OpenAI error metrics (`skuel_openai_errors_total`)
- [ ] Embedding queue metrics (`skuel_embedding_queue_size`)
- [ ] Embeddings processed metrics (`skuel_embeddings_processed_total`)
- [ ] Embedding batch size metrics (`skuel_embedding_batch_size`)
- [ ] Transcription metrics (`skuel_transcription_requests_total`)

### ⏸️ Prometheus Scraping
- [ ] Prometheus successfully scraping SKUEL app
- [ ] Target health: `up` status
- [ ] Scrape duration: <1s

### ⏸️ Alert Firing
- [ ] Simulate high error rate
- [ ] Alert transitions: inactive → pending → firing
- [ ] Alert annotations populate correctly

---

## How to Complete Testing

### 1. Start SKUEL App

```bash
# Option A: Using Poetry (recommended for development)
poetry run python main.py

# Option B: Using Docker
docker compose up -d skuel-app
```

### 2. Verify Metrics Exposed

```bash
# Check all metrics
curl http://localhost:5001/metrics | grep skuel_

# Check AI metrics specifically
curl http://localhost:5001/metrics | grep -E "skuel_(openai|embedding)"
```

### 3. Verify Prometheus Scraping

```bash
# Check target status
curl http://localhost:9090/api/v1/targets | \
  python3 -c "import sys,json; \
  targets=json.load(sys.stdin)['data']['activeTargets']; \
  skuel=[t for t in targets if t['job']=='skuel-app']; \
  print(f\"SKUEL target: {skuel[0]['health'] if skuel else 'NOT FOUND'}\")"

# Expected: "SKUEL target: up"
```

### 4. Test Alert Firing

```bash
# Simulate high error rate
for i in {1..100}; do curl http://localhost:5001/nonexistent; done

# Wait 5 minutes for alert threshold

# Check alerts
curl -s http://localhost:9090/api/v1/alerts | python3 -m json.tool
```

### 5. Run Comprehensive Test Suite

```bash
# Full Phase 1 test suite
./scripts/test_observability_phase1.sh

# Expected: All tests pass (25+ checks)
```

---

## Access Links

### Prometheus
- **Alerts UI**: http://localhost:9090/alerts
- **Targets**: http://localhost:9090/targets
- **Graph Explorer**: http://localhost:9090/graph
- **API**: http://localhost:9090/api/v1/rules

### Grafana
- **Dashboards**: http://localhost:3000
- **Credentials**: admin / admin

### SKUEL
- **Metrics Endpoint**: http://localhost:5001/metrics
- **Application**: http://localhost:5001

---

## Configuration Details

### Prometheus Configuration
```yaml
# /etc/prometheus/prometheus.yml
scrape_configs:
  - job_name: 'skuel-app'
    static_configs:
      - targets: ['skuel-app:8000']  # Docker service name
    scrape_interval: 15s

rule_files:
  - '/etc/prometheus/alerts.yml'
```

### Alert Rules File
```yaml
# /etc/prometheus/alerts.yml
groups:
  - name: skuel_critical
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: (sum(rate(skuel_http_errors_total[5m])) / ...) > 0.05
        for: 5m
        labels:
          severity: critical
      # ... 12 more alerts
```

---

## Troubleshooting

### Issue: Alerts Not Loading

**Symptom**: `curl http://localhost:9090/api/v1/rules` shows empty groups

**Solution**:
```bash
# 1. Check alerts.yml exists in container
docker exec skuel-prometheus test -f /etc/prometheus/alerts.yml && echo "OK" || echo "MISSING"

# 2. If missing, recreate container (not just restart)
docker compose up -d prometheus

# 3. Verify file is mounted
docker exec skuel-prometheus cat /etc/prometheus/alerts.yml | head -10
```

### Issue: SKUEL App Not Reachable

**Symptom**: Prometheus shows target as "down"

**Solution**:
```bash
# 1. Check app is running
curl http://localhost:5001/metrics

# 2. Check target in Prometheus config
docker exec skuel-prometheus cat /etc/prometheus/prometheus.yml | grep targets

# 3. For local dev, use host.docker.internal:8000 instead of skuel-app:8000
```

---

## Validation Summary

| Component | Status | Details |
|-----------|--------|---------|
| Prometheus Container | ✅ Running | Health check passed |
| Configuration File | ✅ Valid | prometheus.yml loaded |
| Alert Rules File | ✅ Mounted | /etc/prometheus/alerts.yml |
| Alert Rules Loaded | ✅ 13/13 | All rules loaded successfully |
| Alert Health | ✅ All OK | Evaluation times <1ms |
| Alert States | ✅ Inactive | Expected (no metrics yet) |
| **SKUEL App** | ⏸️ Pending | Not running |
| **Metrics Exposed** | ⏸️ Pending | Requires app |
| **Scraping Active** | ⏸️ Pending | Requires app |
| **Alerts Can Fire** | ⏸️ Pending | Requires app + metrics |

---

## Next Steps

1. ✅ **DONE**: Prometheus configuration validated
2. ✅ **DONE**: Alert rules loaded and healthy
3. ⏸️ **TODO**: Start SKUEL app
4. ⏸️ **TODO**: Verify metrics exposure
5. ⏸️ **TODO**: Test alert firing
6. ⏸️ **TODO**: Run full test suite (`test_observability_phase1.sh`)
7. 📊 **Future**: Create AI Services Grafana dashboard

---

## Documentation References

- **Complete Implementation**: `/OBSERVABILITY_PHASE1_COMPLETE.md`
- **Changes Summary**: `/OBSERVABILITY_CHANGES_SUMMARY.md`
- **Alerting Guide**: `/.claude/skills/prometheus-grafana/ALERTING.md`
- **Metrics Reference**: `/.claude/skills/prometheus-grafana/SKILL.md`
- **Validation Script**: `/scripts/validate_prometheus_config.sh`
- **Test Suite**: `/scripts/test_observability_phase1.sh`

---

**Test Completed**: 2026-01-31
**Overall Status**: ✅ Prometheus & Alerts Configured Correctly
**Ready for**: Metrics testing (pending app startup)
