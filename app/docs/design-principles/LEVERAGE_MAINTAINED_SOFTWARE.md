---
title: "Design Principle: Leverage Maintained Software"
updated: 2026-08-21
status: current
category: design-principles
tags: [design, principles, open-source, dependencies, maintenance]
related: []
---

# Leverage Maintained Software

> When established, well-maintained software solves a problem, adopt it — don't build a bespoke alternative.

## Statement

SKUEL is built by a non-technical founder through analog-to-digital partnership. Every custom subsystem is a maintenance liability. When open-source software with an active community solves a problem, SKUEL adopts it rather than building a custom solution.

## Why This Matters

Custom code requires custom maintenance. A bespoke metrics system needs custom dashboards, custom alerting, custom query languages. Prometheus + Grafana provide all of that with zero custom code and decades of community knowledge. The founder cannot debug a custom metrics pipeline — but can read Grafana documentation.

## In Practice

| Problem | Custom Alternative (rejected) | Adopted Solution |
|---------|------------------------------|-----------------|
| Graph database | Custom relational schema | Neo4j → AuraDB |
| Observability | Custom logging/dashboards | Prometheus + Grafana |
| UI components | Custom CSS framework | MonsterUI (FrankenUI + Tailwind) |
| Web framework | Custom HTTP server | FastHTML |
| Package management | Poetry (abandoned) | uv |
| Content management | Custom CMS | Obsidian vault + ingestion pipeline |
| Mobile delivery | Native apps / Hyperview | PWA (Web standards) |
| Embeddings | Neo4j plugin | HuggingFace Inference API |

## Decision Criteria

Before building custom:
1. **Does maintained software exist?** Search for established solutions first.
2. **Is it actively maintained?** Check commit frequency, issue response time, community size.
3. **Does it solve 80%+ of the need?** Perfect fit isn't required — 80% coverage with 0% maintenance beats 100% coverage with 100% maintenance.
4. **Can it be replaced later?** Prefer solutions behind interfaces (hexagonal architecture) so the choice isn't permanent.

## Enforcement

- **ADR process:** New infrastructure choices require an ADR documenting alternatives considered
- **SKUEL016:** Linter catches stale references to replaced tools (e.g., Poetry after uv migration)
- **Code review:** Custom implementations of solved problems are rejected

## See Also

- `/docs/decisions/ADR-050-pwa-mobile-strategy.md` — PWA over native apps
