---
updated: 2026-06-12
---

# ADR-046: Activity Domains Connect to Ku via Graph Edges, Not Inheritance

**Status:** Accepted
**Date:** 2026-03-06
**Deciders:** Mike

## Context

SKUEL's Entity Type Architecture includes several groupings: Activity (6), Finance (1), Curriculum (5), Curated Content (1), Organizational (2), and Destination (1). This ADR concerns the relationship between the 6 Activity Domains and Ku specifically.

- **Ku** — atomic knowledge reference node. A single definable thing: concept, state, principle, substance, practice, value. Extends `Entity` directly with 4 fields (`namespace`, `ku_category`, `aliases`, `source`). Shared content, admin-created. (`core/models/ku/ku.py`)

- **Activity Domains** — the 6 user-owned operational entities (Task, Goal, Habit, Event, Choice, Principle). Each has domain-specific fields (scheduling, recurrence, completion logic, context metadata). Extends `UserOwnedEntity(Entity)`.

The question: should Activity entities inherit from Ku, or link to Ku through graph relationships?

## Decision

Activity Domains remain separate dataclasses. Knowledge connections use graph edges from the `RelationshipName` enum (`core/models/relationship_names.py`).

### Per-Domain Knowledge Relationships

| Domain | Relationship(s) | Semantics | Facade Method | Status |
|--------|-----------------|-----------|---------------|--------|
| Tasks | `APPLIES_KNOWLEDGE`, `REQUIRES_KNOWLEDGE` | Applies knowledge to work; knowledge prerequisite | `tasks_service.link_task_to_knowledge()` | Implemented |
| Goals | `REQUIRES_KNOWLEDGE` | Knowledge needed to achieve goal | `goals_service.link_goal_to_knowledge()` | Implemented |
| Habits | `REINFORCES_KNOWLEDGE` | Strengthens knowledge through repetition | `habits_service.link_habit_to_knowledge()` | Implemented |
| Events | `APPLIES_KNOWLEDGE` | Applies knowledge in scheduled context | `events_service.link_event_to_knowledge()` | Implemented |
| Choices | `INFORMED_BY_KNOWLEDGE` | Knowledge informs decision-making | (written at create-time in `choices_core_service`) | Implemented |
| Principles | `GROUNDED_IN_KNOWLEDGE` | Philosophical grounding in knowledge | `principles_service.link_principle_to_knowledge()` | Implemented |

All facade `link_*` methods delegate to `UnifiedRelationshipService` — no inline Cypher on domain backends.

**One edge per domain (single-edge convention).** Each domain writes and reads exactly the edge
in the table above, as defined in `core/models/relationship_registry.py`. There is no separate
"confidence scoring" constant table — the former dead `RelationshipStrength` class in
`core/constants.py` (which named a `PRACTICES_KNOWLEDGE` / `DEVELOPS_KNOWLEDGE` that the registry
never wrote) was deleted; the live `RelationshipStrength` is the `StrEnum` in
`core/models/graph_context.py` (WEAK/MODERATE/STRONG/CRITICAL), unrelated to these edges.

> **Events convergence:** Event→knowledge previously had a split-brain — the study-session path
> (`events_learning_service.create_study_session`) wrote a shadow `PRACTICES_KNOWLEDGE` edge that
> the MEGA-QUERY never read, while the facade / registry wrote `APPLIES_KNOWLEDGE`. The
> `PRACTICES_KNOWLEDGE` edge has been **removed entirely** (One Path Forward): every event→knowledge
> write and read now uses `APPLIES_KNOWLEDGE` (study-session writer, askesis read-map,
> `curriculum_backends.get_practicing_event_uids`). Existing edges are backfilled by
> `scripts/migrations/migrate_event_practices_to_applies_knowledge_2026_06.cypher` — run it
> **before** deploying, since the new readers match only `APPLIES_KNOWLEDGE`.

### Relationship Targets

Knowledge relationships target `:Entity` nodes — both PathSteps (teaching compositions) and atomic Kus (knowledge atoms). A Task can `APPLIES_KNOWLEDGE` to a PathStep about meditation AND to an atomic Ku for "mindfulness." The graph handles this naturally.

### Ku-grain substance derivation

Substance scoring (`KuIntelligenceService.calculate_user_substance`, `PsIntelligenceService`) and ZPD
evidence (`ZPDBackend` current-zone / engaged-uid) reason at **atomic Ku grain** — their contract is
`activity_uid -> [ku_uid, ...]`. But an activity→knowledge edge may target a PathStep (a composition),
not an atomic Ku. To honor the Ku-grain contract, the **read-time queries** (below the hexagonal boundary
in `adapters/persistence/neo4j/`) roll the activity→{Ku|PathStep} relationship up to atomic Kus by
COMPOSING it with the curriculum-internal `PathStep-[:TRAINS_KU|USES_KU]->Ku` composition:

- target already `:Ku` → keep it (1-hop, still valid per *Relationship Targets* above)
- target `:PathStep` → emit the UNION of the Kus it composes via `TRAINS_KU|USES_KU` (2-hop bridge)

This does **not** contradict *Composition Relationships* below — `USES_KU`/`TRAINS_KU` remain
curriculum-internal and unrelated to the activity-to-knowledge pattern. The reader is composing the two
relationship **classes** at read time; neither edge changes meaning. Crediting is full credit per distinct
composed Ku (bounded by the existing per-channel substance caps); the bridge edges carry no importance
property, so no importance-weighting is applied. The reader services consume Ku uids unchanged — only the
queries that feed them were corrected (they previously leaked PathStep uids into the Ku-keyed dicts, so the
Ku-keyed `if ku_uid in ku_list` checks silently matched nothing).

Sites: `user_context_queries.py` MEGA-QUERY (tasks `APPLIES_KNOWLEDGE`, habits
`APPLIES_KNOWLEDGE|REINFORCES_KNOWLEDGE`, events `APPLIES_KNOWLEDGE`, choices `INFORMED_BY_KNOWLEDGE`,
principles `GROUNDED_IN_KNOWLEDGE`) and `zpd_backend.py` (`_ZONE_QUERY`, `_TARGETED_KU_ENGAGEMENT_QUERY`:
task `APPLIES_KNOWLEDGE`, habit `REINFORCES_KNOWLEDGE`).

### Composition Relationships (Separate Concern)

PathStep-to-Ku composition uses dedicated relationship types:
- `(PathStep)-[:USES_KU]->(Ku)` — path step composes atomic Kus into narrative
- `(PathStep)-[:TRAINS_KU]->(Ku)` — path step trains specific Kus

These are curriculum-internal and unrelated to the Activity-to-Knowledge pattern.

## Rationale

### 1. Identity semantics stay clean
A Task is "work to be done." A Ku is "a definable knowledge unit." These are different identities with different ownership models (`UserOwnedEntity` vs shared `Entity`), different `ContentScope` values (`USER_OWNED` vs `SHARED`), and different `ContentOrigin` tiers (`USER_CREATED` vs `CURRICULUM`).

### 2. Graph-native modeling fits this relationship
"Applies knowledge" is contextual and many-to-many. A single Task may apply multiple Kus; a single Ku may be applied by many Tasks across many users. Graph edges express this cleanly. Inheritance would force a 1:1 identity relationship where a many:many contextual one belongs.

### 3. Domain-specific evolution stays independent
Activity domains evolve with scheduling, recurrence, completion logic, assessment. Ku evolves with namespace, category, aliases. Inheritance would couple these evolution paths. Separate dataclasses with graph edges keep them independent.

### 4. Existing architecture already follows this pattern
Four of six Activity Domains already have `link_*_to_knowledge()` backend methods in `backends/activity_backends.py`. The MEGA-QUERY already traverses `APPLIES_KNOWLEDGE` and `REQUIRES_KNOWLEDGE` edges. This ADR formalizes what's already working.

## Decision Heuristic

When modeling a new concept:

- **Is it a stable, reusable knowledge atom?** (definable thing, no user ownership, admin-created) -> Model as `Ku`
- **Is it a user action/plan/event that references knowledge?** (user-owned, domain-specific fields) -> Model as Activity Domain dataclass + knowledge relationship edges

## Implementation Status

All six Activity Domains now link to knowledge: the MEGA-QUERY (`user_context_queries.py`) traverses
the Choice (`INFORMED_BY_KNOWLEDGE`) and Principle (`GROUNDED_IN_KNOWLEDGE`) edges alongside Task/Habit/Event,
and ingestion wires all six via the per-domain core services. The original
"remaining work" (choice/principle backend link methods, confidence constants, MEGA-QUERY traversals) is done.

## Key Files

- `core/models/ku/ku.py` — Ku(Entity) atomic knowledge model
- `core/models/entity.py` — Entity base class
- `core/models/relationship_names.py` — RelationshipName enum
- `adapters/persistence/neo4j/backends/activity_backends.py` — Backend link methods
- `core/models/relationship_registry.py` — per-domain knowledge edge definitions (single-edge convention)
- `adapters/persistence/neo4j/user_context_queries.py` — MEGA-QUERY knowledge traversals
- `adapters/persistence/neo4j/zpd_backend.py` — ZPD zone / engagement Ku-grain traversals

## Related

- ADR-041: Unified Ku Model
- `docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`
- `docs/architecture/ENTITY_TYPE_ARCHITECTURE.md`
