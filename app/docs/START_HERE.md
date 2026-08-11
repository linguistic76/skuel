---
title: Start Here — New Developer Onboarding
updated: 2026-03-20
status: current
category: onboarding
tags: [onboarding, getting-started, newcomer]
related:
- architecture/ENTITY_TYPE_ARCHITECTURE.md
- tutorials/DATA_FLOW_WALKTHROUGH.md
- development/STARTUP.md
---

# Start Here

SKUEL is a knowledge-centric productivity platform where every feature connects to learning. Users create activities (Tasks, Goals, Habits), study curriculum (PathSteps, Exercises), submit work, receive feedback, and refine — all grounded in a knowledge graph stored in Neo4j.

Read this page first, then follow the links in order.

---

## 1. What SKUEL Is Built From

| Layer | Technology | Where |
|-------|-----------|-------|
| Web framework | FastHTML (Python, server-rendered HTML) | `adapters/inbound/` |
| UI interactivity | HTMX + Alpine.js | `static/js/`, `ui/` |
| Styling | Tailwind CSS (pre-compiled `output.css`) + Lucide icons | `static/css/`, `ui/components/` |
| Database | Neo4j (graph database) | `adapters/persistence/neo4j/` |
| Domain logic | Python services + frozen dataclasses | `core/services/`, `core/models/` |
| Package manager | uv | `pyproject.toml`, `uv.lock` |

Run the app: `./dev up-neo4j` (Terminal 1), then `./dev serve` (Terminal 2). See [STARTUP.md](development/STARTUP.md) for details.

---

## 2. The 25 Entity Types

Everything in SKUEL is an **Entity** — a frozen Python dataclass stored as a Neo4j node. The `entity_type` field says which kind it is. There are 25 types in six groups:

**Activities** (user-owned, daily life): Task, Goal, Habit, Event, Choice, Principle

**Activity Templates** (PS-owned, spawn Activity instances on engagement): TaskTemplate, GoalTemplate, HabitTemplate, EventTemplate, ChoiceTemplate, PrincipleTemplate

**Curriculum** (admin-created, shared): Ku, PathStep, LearningPath, Exercise

**Forms**: FormTemplate, FormSubmission

**Submissions & Reports** (the learning loop): UserEntry, EntryReport, ActivityReport, RevisedExercise, Interaction

**Other**: Resource, LifePath

Groups is *not* an EntityType — it lives in `NonKuDomain` (ADR-053), alongside Finance, Calendar, and Learning.

The learning loop is SKUEL's core purpose (4 phases): **Exercise → UserEntry → EntryReport → RevisedExercise → ...** PathStep is the curriculum anchor, linked via `(PathStep)-[:HAS_EXERCISE]->(Exercise)`. See [Learning Loop Architecture](architecture/LEARNING_LOOP_ARCHITECTURE.md).

Full reference: [Entity Type Architecture](architecture/ENTITY_TYPE_ARCHITECTURE.md)

---

## 3. How a Request Flows

A request passes through four layers:

```
HTTP request
  → Route handler        (adapters/inbound/*_api.py or *_ui.py)
    → Service            (core/services/{domain}/)
      → Backend          (adapters/persistence/neo4j/)
        → Neo4j
```

**Routes** validate input with Pydantic models, call a service, and return HTML or JSON.
**Services** contain business logic. Activity domains use a facade with sub-services (.core, .search, .intelligence).
**Backends** translate service calls into Cypher queries and run them against Neo4j.

Follow an actual request end-to-end: [Data Flow Walkthrough](tutorials/DATA_FLOW_WALKTHROUGH.md)

---

## 4. Key Patterns to Know

These four patterns appear everywhere. Learn them early:

**Result[T]** — Services return `Result[T]` instead of raising exceptions. Check `.is_error`, access `.value` on success, `.error` on failure. See [Error Handling](patterns/ERROR_HANDLING.md).

**Frozen dataclasses** — Domain models are immutable. Created once, never mutated. New state means a new instance. See [Three-Tier Type System](patterns/three_tier_type_system.md).

**Three type tiers** — Pydantic models validate input at the edge, DTOs move data between layers, frozen dataclasses hold domain state. Each tier has a job.

**DomainConfig** — Each service's behavior (search fields, DTO class, model class) is defined in a config object, not scattered across methods. See [BaseService Quick Start](guides/BASESERVICE_QUICK_START.md).

---

## 5. Where Things Live

| You want to... | Look in |
|----------------|---------|
| Find a route handler | `adapters/inbound/{domain}_api.py` or `{domain}_ui.py` |
| Find domain logic | `core/services/{domain}/` |
| Find a data model | `core/models/{domain}/` |
| Find a protocol/interface | `core/ports/` |
| Find UI components | `ui/` (Python functions that return HTML) |
| Find static assets | `static/` |
| Find how services wire together | `services_bootstrap/` |
| Run commands | `./dev help` |

---

## Next Steps

Once you've read the links above, explore based on what you're working on:

- **Building UI?** → [UI Component Patterns](patterns/UI_COMPONENT_PATTERNS.md), [Component Catalog](ui/COMPONENT_CATALOG.md)
- **Adding a service?** → [BaseService Quick Start](guides/BASESERVICE_QUICK_START.md)
- **Working with Neo4j?** → [Query Architecture](patterns/query_architecture.md)
- **Understanding a design decision?** → [ADR index](decisions/) (52 Architecture Decision Records)
- **Curated documentation index** → [INDEX.md](INDEX.md) (hand-maintained, not a full listing)
