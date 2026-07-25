---
title: Readme
related_skills:
  - prometheus-grafana
---
# SKUEL Observability Stack

**Prometheus + Grafana** monitoring for SKUEL's production infrastructure.

---

## Quick Start

**Skill:** [@prometheus-grafana](../.claude/skills/prometheus-grafana/SKILL.md)

### 1. Start the Monitoring Stack

Prometheus and Grafana are behind the `monitoring` profile — they don't start with a plain `docker compose up`.

```bash
# From project root
./dev up-monitoring -d               # Neo4j + App + Prometheus + Grafana
# or directly:
docker compose --profile monitoring up -d

# Verify services running
docker compose --profile monitoring ps
```

### 2. Access UIs

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)

### 3. Verify Metrics

```bash
# Check SKUEL metrics (dev app on 8000; 5001 is the production container port)
curl http://localhost:8000/metrics | grep skuel_

# Validate configuration
./scripts/validate_prometheus_config.sh
```

---

## One Surface: Prometheus

`/metrics` is THE metrics surface — the former JSON metrics routes
(`/api/monitoring/*`, `/api/metrics`) were folded into Prometheus. For ad-hoc
checks without Grafana, grep the text exposition directly:

```bash
# Embedding worker queue depth + processed counters (e.g. during a re-embed —
# see /docs/operations/EMBEDDING_VERSION_UPGRADE.md)
curl -s http://localhost:8000/metrics | grep skuel_embedding
```

**Production:** the droplet runs no Prometheus/Grafana, and Caddy blocks `/metrics`
from the public internet (it leaks internal telemetry). Read it from inside the
stack: `docker compose exec skuel-app curl -s localhost:5001/metrics`. The AuraDB
cap alerts are evaluated in-app instead (poller check, WARNING 80% / ERROR 95% —
`grep 'AuraDB cap'` the app logs; see the prometheus-grafana skill's ALERTING.md).

---

## What's Inside

**Metrics**: 40 across 7 categories (HTTP, DB, Events, Domains, Graph incl. knowledge health, Queries, AI)
**Alerts**: 14 alerting rules with runbooks (incl. AuraDB Free cap alerts)
**Dashboards**: 4 Grafana dashboards (System Health, Domain Activity, Graph Health, Event Bus)

**See**: `/.claude/skills/prometheus-grafana/SKILL.md` for complete reference

---

## Files

- `prometheus.yml` - Scrape config (Docker deployment)
- `prometheus.dev.yml` - Development config (host-run app)
- `alerts.yml` - 14 alerting rules (+1 commented-out SLO rule)
- `grafana/dashboards/` - 4 pre-built dashboards

---

## Resources

- **SKILL.md** - Complete metrics reference
- **ALERTING.md** - Alert runbooks and patterns
- `scripts/validate_prometheus_config.sh` - Config validation
- `scripts/test_observability_phase1.sh` - Test suite

---

**Last Updated**: 2026-07-24 (post-PR #803 one-surface consolidation)
**Status**: Production Ready ✅
