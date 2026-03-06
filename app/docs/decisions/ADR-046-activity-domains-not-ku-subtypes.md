# ADR-046: Activity Domains Connect to Ku via Graph Edges, Not Inheritance

**Status:** Accepted
**Date:** 2026-03-06
**Deciders:** Mike

## Context

SKUEL's Entity Type Architecture includes several domain categories: Activity (5), Scheduling (1), Finance (1), Curriculum (4), Content (1), Organizational (2), and Destination (1). This ADR concerns the relationship between the 5 Activity Domains and Ku specifically.

- **Ku** — atomic knowledge reference node. A single definable thing: concept, state, principle, substance, practice, value. Extends `Entity` directly with 4 fields (`namespace`, `ku_category`, `aliases`, `source`). Shared content, admin-created. (`core/models/ku/ku.py`)

- **Activity Domains** — the 5 user-owned operational entities (Task, Goal, Habit, Choice, Principle). Each has domain-specific fields (scheduling, recurrence, completion logic, context metadata). Extends `UserOwnedEntity(Entity)`. Events (the scheduling/integration layer) also connects to knowledge through the same pattern.

The question: should Activity entities inherit from Ku, or link to Ku through graph relationships?

## Decision

Activity Domains remain separate dataclasses. Knowledge connections use graph edges from the `RelationshipName` enum (`core/models/relationship_names.py`).

### Per-Domain Knowledge Relationships

| Domain | Relationship(s) | Semantics | Backend Method | Status |
|--------|-----------------|-----------|----------------|--------|
| Tasks | `APPLIES_KNOWLEDGE`, `REQUIRES_KNOWLEDGE` | Applies knowledge to work; knowledge prerequisite | `link_task_to_knowledge()` | Implemented |
| Goals | `REQUIRES_KNOWLEDGE` | Knowledge needed to achieve goal | `link_goal_to_knowledge()` | Implemented |
| Habits | `REINFORCES_KNOWLEDGE` | Strengthens knowledge through repetition | `link_habit_to_knowledge()` | Implemented |
| Events | `REINFORCES_KNOWLEDGE` | Practices knowledge in scheduled context | `link_event_to_knowledge()` | Implemented |
| Choices | `INFORMS_CHOICE` | Knowledge informs decision-making | — | Not yet implemented |
| Principles | `GROUNDED_IN_KNOWLEDGE` | Philosophical grounding in knowledge | — | Not yet implemented |

Confidence scoring for these relationships is defined in `RelationshipStrength` in `core/constants.py`:
- `APPLIES_KNOWLEDGE: 0.85` (Task applies knowledge)
- `PRACTICES_KNOWLEDGE: 0.9` (Event practices knowledge)
- `DEVELOPS_KNOWLEDGE: 0.9` (Habit develops knowledge)
- `DEFAULT: 0.7` (generic fallback)

### Relationship Targets

Knowledge relationships target `:Entity` nodes — both Articles (teaching compositions) and atomic Kus (knowledge atoms). A Task can `APPLIES_KNOWLEDGE` to an Article about meditation AND to an atomic Ku for "mindfulness." The graph handles this naturally.

### Composition Relationships (Separate Concern)

Article-to-Ku composition uses dedicated relationship types:
- `(Article)-[:USES_KU]->(Ku)` — article composes atomic Kus into narrative
- `(LearningStep)-[:TRAINS_KU]->(Ku)` — learning step trains specific Kus

These are curriculum-internal and unrelated to the Activity-to-Knowledge pattern.

## Rationale

### 1. Identity semantics stay clean
A Task is "work to be done." A Ku is "a definable knowledge unit." These are different identities with different ownership models (`UserOwnedEntity` vs shared `Entity`), different `ContentScope` values (`USER_OWNED` vs `SHARED`), and different `ContentOrigin` tiers (`USER_CREATED` vs `CURRICULUM`).

### 2. Graph-native modeling fits this relationship
"Applies knowledge" is contextual and many-to-many. A single Task may apply multiple Kus; a single Ku may be applied by many Tasks across many users. Graph edges express this cleanly. Inheritance would force a 1:1 identity relationship where a many:many contextual one belongs.

### 3. Domain-specific evolution stays independent
Activity domains evolve with scheduling, recurrence, completion logic, assessment. Ku evolves with namespace, category, aliases. Inheritance would couple these evolution paths. Separate dataclasses with graph edges keep them independent.

### 4. Existing architecture already follows this pattern
Four of six Activity Domains already have `link_*_to_knowledge()` backend methods in `domain_backends.py`. The MEGA-QUERY already traverses `APPLIES_KNOWLEDGE` and `REQUIRES_KNOWLEDGE` edges. This ADR formalizes what's already working.

## Decision Heuristic

When modeling a new concept:

- **Is it a stable, reusable knowledge atom?** (definable thing, no user ownership, admin-created) -> Model as `Ku`
- **Is it a user action/plan/event that references knowledge?** (user-owned, domain-specific fields) -> Model as Activity Domain dataclass + knowledge relationship edges

## Implementation: Remaining Work

1. Add `link_choice_to_knowledge()` to `ChoicesBackend` using `INFORMS_CHOICE`
2. Add `link_principle_to_knowledge()` to `PrinciplesBackend` using `GROUNDED_IN_KNOWLEDGE`
3. Add confidence scoring constants for Choices and Principles in `core/constants.py`
4. Wire MEGA-QUERY Choice-to-Knowledge and Principle-to-Knowledge traversals in `user_context_queries.py`

## Key Files

- `core/models/ku/ku.py` — Ku(Entity) atomic knowledge model
- `core/models/entity.py` — Entity base class
- `core/models/relationship_names.py` — RelationshipName enum
- `adapters/persistence/neo4j/domain_backends.py` — Backend link methods
- `core/constants.py` — RelationshipStrength confidence scoring
- `core/services/user/user_context_queries.py` — MEGA-QUERY knowledge traversals

## Related

- ADR-041: Unified Ku Model
- `docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`
- `docs/architecture/ENTITY_TYPE_ARCHITECTURE.md`
