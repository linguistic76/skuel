---
title: Knowledge-Health Gauge
updated: 2026-08-07
status: current
category: tools
tags: [analytics, knowledge, graph, authoring, gds, adr-080]
related: [HEALTH_CHECKS.md]
---

# Knowledge-Health Gauge

**Status:** ✅ Active (ADR-080 Horizon 1)
**Location:** `scripts/knowledge_health_report.py` (CLI) → `core/services/analytics/knowledge_health_service.py` (service)
**Run:** `./dev knowledge-health [--json]`

One consolidated, corpus-level structural-health report over the knowledge
subgraph (Ku / PathStep / LearningPath / Exercise — authored content only,
user-generated data and telemetry excluded): node counts, Ku degree
distribution, orphan Kus, composition / prerequisite-DAG / ORGANIZES / lateral
coverage, practice coverage, and a composite GDS-readiness score with
authoring-guidance flags. Pure graph analytics — CORE-tier safe, no API keys.

Not to be confused with `./dev health` (codebase rot — see
[HEALTH_CHECKS.md](/docs/tools/HEALTH_CHECKS.md)): this gauge measures the
*content graph*, and doubles as the density gate for the deferred GDS work.

**Other surfaces:** admin page `/admin/knowledge-health`; 6 knowledge-scoped
Prometheus gauges fed by the 5-minute graph-health poller.

**See:** [ADR-080](/docs/decisions/ADR-080-auradb-three-horizon-strategy.md) § Horizon 1
