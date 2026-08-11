---
title: "Design Principle: Type Safety as Ontology"
updated: 2026-03-28
status: current
category: design-principles
tags: [design, principles, type-safety, enums, mypy]
related: [docs/architecture/TYPE_SAFETY_DESIGN_PHILOSOPHY.md, docs/patterns/TYPE_SAFETY_OVERVIEW.md]
---

# Type Safety as Ontology

> Enums and types define what the app *is*, not just what it accepts.

## Statement

SKUEL's type system is not annotation overhead — it is the machine-readable specification of the domain. `EntityType` defines what entities exist. `EntityStatus` defines what states they can be in. `UserRole` defines who can do what. When these enums change, the app's capabilities change. A type error from MyPy reveals a real design problem, not an annotation oversight.

## Why This Matters

In a system with 25 entity types, 14 statuses, 4 roles, and 6 lateral relationship types, raw strings create invisible coupling. `entity_type == "task"` compiles fine even when `EntityType.TASK` has been renamed or removed. `entity_type == EntityType.TASK` fails immediately at the type checker, before any code runs.

For a system targeting 10,000 users, enum-driven pipelines enable:
- **Monitoring:** Every entity creation, status transition, and search query is typed — dashboards can aggregate by enum value
- **Analysis:** Cross-domain intelligence services reason about `EntityType`, not strings
- **Autonomy:** Pipelines of entity interactions are verifiable at compile time

## The Core Enums

| Enum | Purpose | Count |
|------|---------|-------|
| `EntityType` | What kind of entity | 20 values |
| `EntityStatus` | What state it's in | 14 values |
| `UserRole` | Who can do what | 4 levels |
| `ContentOrigin` | Where content comes from | 4 tiers |
| `ContentScope` | Who can access it | USER_OWNED / SHARED |
| `RelationshipName` | How entities connect | 6 lateral types + domain relationships |
| `Priority` | How urgent/important | Ordered enum with color methods |
| `NonKuDomain` | Non-entity domains | 4 values (Finance, Group, Calendar, Learning) |

## In Practice

- **No raw string comparisons:** `entity_type == EntityType.TASK`, never `entity_type == "task"`
- **Enum methods carry behavior:** `EntityStatus.is_terminal()`, `Priority.get_color()`, `EntityType.is_activity()`
- **Branded identifiers:** `UserUID = NewType("UserUID", str)` — prevents passing a task UID where a user UID is expected
- **Protocol return types:** 159 TypedDicts in `core/ports/query_types.py` — no `Result[Any]` in protocols
- **Three-tier type system:** Pydantic at edges, frozen dataclasses at core, DTOs between

## Enforcement

- **MyPy:** 0 errors enforced in CI. `core.services.*` and `core.ports.*` require `disallow_untyped_defs`
- **SKUEL linter:** SKUEL013 (use `RelationshipName` enum), SKUEL014 (use `EntityType`/`NonKuDomain` enum)
- **Any policy:** Category A (eliminate), B (use specific type), C (permanent boundary with `# boundary:` comment)
- **Ruff:** Formatting enforced via `./dev format`

## Current Gaps (2026-03-28)

See the companion audit for specific gaps being addressed:
- ~11 function parameters typed `str` that should use `EntityType` or `EntityStatus`
- ~5 bare `list` returns without type parameters
- ~7 `Result[Any]` patterns in services (should be specific types)
- Missing `TriggerType` enum for principle reflections

## See Also

- `/docs/architecture/TYPE_SAFETY_DESIGN_PHILOSOPHY.md` — full philosophy document
- `/docs/patterns/TYPE_SAFETY_OVERVIEW.md` — implementation guide
- `/docs/patterns/ANY_USAGE_POLICY.md` — policy on `Any` usage
- `CLAUDE.md` § "Type Safety Architecture"
