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

```bash
# From project root
docker compose up -d prometheus grafana

# Verify services running
docker compose ps
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
