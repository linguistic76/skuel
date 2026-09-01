---
title: Type Safety Design Philosophy
created: 2026-03-27
updated: 2026-08-11
status: active
audience: all
tags: [architecture, type-safety, philosophy, ontology, security, dsl]
related: [TYPE_SAFETY_OVERVIEW.md, ANY_USAGE_POLICY.md, three_tier_type_system.md, knowledge_substance_philosophy.md]
---

# Type Safety Design Philosophy

## Core Thesis: "Types define what the app is doing"

**Types in SKUEL are not annotation overhead — they are the domain model made concrete.** Every frozen dataclass, every protocol, every enum encodes a decision about what this system *is* and how its parts relate. The ability to define types results in the app acting as intended. The type system is the ontology rendered as code.

This document explains *why* SKUEL values type safety and *when* to apply it. For implementation patterns, see the cross-references at the end.

---

## Types as Ontology

SKUEL is built on a developing ontology — entity types, behavioral traits, relationship patterns, and cross-cutting systems that together describe a learner's world. The type system is how that ontology becomes executable:

| Ontological Concept | Type Expression |
|---------------------|-----------------|
| "Things come in distinct kinds" | `EntityType` enum |
| "Some things are owned by users" | `UserOwnedEntity(Entity)` base class |
| "Entities have behavioral traits" | `is_activity()`, `is_processable()`, `requires_user_uid()` methods |
| "Services have defined contracts" | 65+ protocols in `core/ports/` |
| "Query results have known shapes" | 159 TypedDicts in `core/ports/query_types.py` |
| "The learning loop has 4 phases" | `Exercise -> UserEntry -> EntryReport -> RevisedExercise` type chain (anchored to PathStep via `Exercise.path_step_uid`) |

When the ontology evolves — a new entity type, a new relationship, a new behavioral trait — the type system evolves with it. A MyPy error after such a change is not noise; it's the system telling you where the old ontology assumptions no longer hold. This is why SKUEL's core principle for type safety is: *"A type error from MyPy reveals a real design problem, not an annotation oversight."*

---

## The Raw-to-Typed Lifecycle

**Design Principle:** Content and interactions are allowed to exist RAW and undefined. Through experience and instances, patterns get recognized and become typed.

This is deliberate. SKUEL does not label what is happening before the instance reveals itself. The type system grows *after* the domain is understood, not before.

### How This Works in Practice

The Activity DSL is the purest expression of this lifecycle:

```
RAW (user writes):     "- [ ] Read chapter 5 @context(task) @priority(1)"
PARSED (validated):     Pydantic model extracts tags, validates structure
TYPED (domain model):   Task(frozen dataclass) with typed fields
STORED (graph):         :Entity:Task node with typed properties
```

The three-tier type system mirrors this raw-to-typed progression:

| Tier | Role in Lifecycle |
|------|-------------------|
| **Pydantic** (external edge) | Receives raw input, validates, fails fast |
| **DTOs** (transfer) | Mutable intermediary — data taking shape |
| **Frozen domain models** (core) | The fully typed, immutable definition |

### What This Means for Development

When building a new feature or domain area:

1. **Start with the interaction.** Let users do the thing. Use `dict[str, Any]` at boundaries if needed.
2. **Observe the patterns.** What fields recur? What constraints emerge? What breaks?
3. **Type what you've learned.** Create the frozen dataclass, the protocol, the TypedDict.
4. **Delete the flexible version.** One Path Forward — no legacy wrappers alongside the typed version.

This is not an excuse for laziness. Once a pattern is understood, it gets typed. Untyped code that *could* be typed is technical debt, not philosophical flexibility.

---

## Security Through Types

**Security in SKUEL is intrinsic, not an add-on.** The type system is part of the security model.

### How Types Enforce Security

**Identity boundaries:** `UserUID` is a distinct `NewType` — it cannot accidentally be used where an `EntityUID` is expected. This prevents authorization bugs at the type level, before any runtime check.

```python
# From core/models/type_hints.py
UserUID = NewType("UserUID", str)

# A function expecting UserUID won't accept a bare string or EntityUID
def get_user_context(user_uid: UserUID) -> Result[UserContext]: ...
```

**Ownership discrimination:** The `UserOwnedEntity` / `Entity` type hierarchy determines which entities require ownership verification. Routes that accept a `UserOwnedEntity` *must* verify ownership — the type makes this requirement visible.

**Enum-enforced states:** `UserRole`, `ContentScope`, `EntityStatus`, `ContentOrigin`, `ExerciseScope`, and `EnrichmentMode` are enums, not strings. Invalid role escalation, unauthorized content access, and illegal state transitions are caught by the type checker:

| Security Concern | Type Defense |
|-----------------|--------------|
| User impersonation | `UserUID` NewType — can't pass entity UID as user UID |
| Unauthorized access | `ContentScope` enum — PRIVATE/SHARED/PUBLIC enforced |
| Privilege escalation | `UserRole` enum — REGISTERED/MEMBER/TEACHER/ADMIN ordered |
| Invalid state transitions | `EntityStatus.can_transition_to()` — typed state machine |
| Content origin confusion | `ContentOrigin` enum — CURATED vs USER_CREATED can't be mixed |
| Exercise scope confusion | `ExerciseScope` enum — PERSONAL vs ASSIGNED enforced at Pydantic boundary and all comparisons |

**The principle:** Every security boundary that can be expressed as a type *should* be expressed as a type. Runtime checks are the fallback for what types can't reach (network boundaries, database queries). Types are the first line of defense.

---

## When NOT to Type

Type safety is a solid foundation that evolves — not a cage that constrains.

### Deliberate Flexibility

Some boundaries are intentionally untyped:

- **Category C (permanent boundaries):** External library returns, Neo4j driver values, JSON from third-party APIs. These live at the edge of SKUEL's control. The `Any` Usage Policy documents these with `# boundary:` comments.
- **Emerging patterns:** When a new domain area is being explored and the shape of data is not yet clear, flexibility is appropriate. But this is a *temporary* state — once the pattern is understood, types follow.
- **Graph properties:** Neo4j returns `dict[str, Any]` by nature. SKUEL narrows these at the backend boundary with explicit `int()`/`float()`/`str()` casts, converting untyped graph data into typed domain models.

### What This Is NOT

This is not permission to:
- Leave `Any` in service-layer code that has well-understood contracts
- Skip typing protocol returns when the shape is known
- Use `dict[str, Any]` as a service return type when a TypedDict would be precise
- Avoid MyPy errors by loosening configuration instead of fixing the code

The test: *Could this be typed today?* If yes, type it. If the domain hasn't revealed the pattern yet, leave space — but mark it for future typing.

---

## Current Maturity

SKUEL's type safety has reached a solid, production-grade foundation:

| Milestone | Status |
|-----------|--------|
| 0 MyPy errors baseline | Achieved March 2026 (down from 2,247) |
| Three-tier type system | Enforced across all entity types |
| Protocol-based DI | 65+ protocols, 100% protocol-mixin alignment |
| Typed protocol returns | ~170 methods return specific models/TypedDicts, 0 `Result[Any]` in protocols (1 intentional in `base_service_interface.py`). Service-layer `Result[Any]` also narrowed to concrete types |
| Query type coverage | 159 TypedDicts (21 input, 138 output) |
| Any usage policy | Three categories with enforcement |
| Security NewTypes | `UserUID` propagated to ~1,930 annotations across 313 files; `EntityUID` to ~200 annotations (including variant names like `parent_entity_uid`, `source_entity_uid`). All layers enforce `UserUID` — auth, REST, services, backends, ingestion |
| Enum-enforced boundaries | `UserRole`, `ExerciseScope`, `EntityStatus`, `Pipeline`, `ReportSource`, `Visibility`, `SubmissionModality`, `FeedbackCategory`, `MasteryImpact`, `EnrichmentMode` — zero raw string comparisons for roles, scopes, status checks, pipeline, visibility levels, modalities, feedback categorization, mastery scoring, enrichment modes |
| Search protocol generics | All 6 `DomainSearchOperations` extensions parameterized with domain model type (`Goal`, `Event`, `Choice`, `Principle`, `Task`, `Habit`), not `Entity` |

This foundation is valued and allowed to evolve. As the ontology grows — new entity types, new relationships, new cross-cutting systems — the type system grows with it. The goal is not perfection frozen in place, but a living system where types track the domain as it reveals itself.

---

## Cross-References

### Implementation Patterns (the *how*)
- [Type Safety Overview](../patterns/TYPE_SAFETY_OVERVIEW.md) — executive summary of the three systems
- [Any Usage Policy](../patterns/ANY_USAGE_POLICY.md) — three-category policy with enforcement
- [Three-Tier Type System](../patterns/three_tier_type_system.md) — Pydantic/DTO/domain architecture
- [MyPy Type Safety Patterns](../patterns/MYPY_TYPE_SAFETY_PATTERNS.md) — proven error reduction patterns
- [MyPy Pragmatic Strategy](../patterns/mypy_pragmatic_strategy.md) — per-module strictness approach
- [Protocol Architecture](../patterns/protocol_architecture.md) — protocol-based dependency injection

### Related Philosophy (the *why*)
- [Knowledge Substance Philosophy](knowledge_substance_philosophy.md) — ontological hierarchy and applied knowledge
- [Activity DSL Specification](../dsl/DSL_SPECIFICATION.md) — the raw-to-typed lifecycle in action
- [Entity Type Architecture](ENTITY_TYPE_ARCHITECTURE.md) — the entity types and behavioral traits
