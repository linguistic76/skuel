---
title: SKUEL Design Principles
updated: 2026-03-29
status: current
category: design-principles
tags: [design, principles, philosophy, architecture]
related: [CLAUDE.md, docs/architecture/TYPE_SAFETY_DESIGN_PHILOSOPHY.md]
---

# SKUEL Design Principles

Core principles that govern every technical decision in SKUEL. These are not aspirational — they are enforced in code, linting, and review.

## The Principles

| # | Principle | One-Line Summary |
|---|-----------|-----------------|
| 1 | [One Path Forward](ONE_PATH_FORWARD.md) | When a better pattern emerges, the old one is deleted entirely |
| 2 | [Fail Fast](FAIL_FAST.md) | Dependencies are required. Errors surface immediately with clear reports |
| 3 | [Leverage Maintained Software](LEVERAGE_MAINTAINED_SOFTWARE.md) | Adopt established open-source software; don't build bespoke alternatives |
| 4 | [Type Safety as Ontology](TYPE_SAFETY_AS_ONTOLOGY.md) | Enums and types define what the app *is*, not just what it accepts |
| 5 | [Limited Backward Compatibility](LIMITED_BACKWARD_COMPATIBILITY.md) | No legacy wrappers, no deprecation periods, no historical references |
| 6 | [Analog-Digital Independence](ANALOG_DIGITAL_INDEPENDENCE.md) | The app runs at full capability without any paid API dependency |
| 7 | [Hub Pages](HUB_PAGES.md) | Pages are navigation — curated links replace persistent chrome |

## How Principles Relate

```
One Path Forward ──────► Limited Backward Compatibility
       │                         │
       ▼                         ▼
  Fail Fast              Type Safety as Ontology
       │                         │
       ▼                         ▼
Leverage Maintained    Analog-Digital Independence
    Software                     │
                                 ▼
                            Hub Pages
```

**One Path Forward** drives **Limited Backward Compatibility** — you can't have one path if you maintain old paths. **Fail Fast** ensures problems surface before they compound. **Type Safety as Ontology** makes the domain structure machine-verifiable. **Leverage Maintained Software** reduces the surface area that needs human maintenance. **Analog-Digital Independence** ensures the core system works at $0. **Hub Pages** extends Analog-Digital Independence into UI — pages with links are the simplest, most standards-compliant navigation pattern.

## Enforcement

Each principle includes its enforcement mechanisms: linter rules, MyPy checks, CI gates, or code review patterns. Principles without enforcement are aspirations, not principles.
