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
# Check SKUEL metrics
curl http://localhost:5001/metrics | grep skuel_

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
curl -s http://localhost:5001/metrics | grep skuel_embedding
```

**Production:** the droplet runs no Prometheus/Grafana, and Caddy blocks `/metrics`
from the public internet (it leaks internal telemetry). Read it from inside the
stack: `docker compose exec skuel-app curl -s localhost:5001/metrics`.

---

## What's Inside

**Metrics**: 43 across 9 categories (System, HTTP, DB, Events, Domains, Graph, Search, Queries, AI)
**Alerts**: 14 production alerts with runbooks
**Dashboards**: 4 Grafana dashboards (System, Domain, Graph, Search & Events)

**See**: `/.claude/skills/prometheus-grafana/SKILL.md` for complete reference

---

## Files

- `prometheus.yml` - Production config (Docker deployment)
- `prometheus.dev.yml` - Development config (local app)
- `alerts.yml` - 14 production alerts
- `grafana/dashboards/` - 4 pre-built dashboards

---

## Resources

- **SKILL.md** - Complete metrics reference
- **ALERTING.md** - Alert runbooks and patterns
- `scripts/validate_prometheus_config.sh` - Config validation
- `scripts/test_observability_phase1.sh` - Test suite

---

**Last Updated**: 2026-01-31 (Phase 1 Complete)
**Status**: Production Ready ✅
