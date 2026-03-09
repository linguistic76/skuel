# ADR-047: Entity Types Replace Domain Categories

**Status:** Accepted
**Date:** 2026-03-07
**Deciders:** Mike

**Decision Type:** Pattern/Practice

**Related ADRs:**
- Related to: ADR-046 (Activity Domains connect to Ku via graph edges)
- Related to: ADR-041 (Unified Ku model)

---

## Context

SKUEL's architecture documentation described "14 domains in 7 categories" — Activity (5), Scheduling (1), Finance (1), Curriculum (4), Content (1), Organizational (2), Destination (1). This framing imposed a rigid taxonomy on entity types that contradicts SKUEL's core philosophy of decentralization, emergence, and learner-directed exploration.

Problems with the domain-category framing:

1. **"Domain" has no enum.** There is no `Domain` enum with 14 values. The actual code discriminator is `EntityType` (17 values). "Domain" was a documentation concept with no formal definition.

2. **Category boundaries are arbitrary.** Is Exercise "Curriculum" or "Instruction"? Is Resource "Curriculum" or "Curated Content"? These questions have no meaningful answer — the categories are imposed labels, not emergent structure.

3. **Categories contradict graph-native thinking.** In a graph database, identity comes from relationships, not from category membership. An Exercise connects to an Article via `FOR_CURRICULUM`, to a Group via `FOR_GROUP`, and to a Submission via `FULFILLS_EXERCISE`. Its identity IS those relationships, not a label like "Instruction Domain."

4. **Categories conflict with SKUEL's pedagogical philosophy.** SKUEL implements choose-your-own-adventure learning — decentralization and emergence over hierarchy and silos. Forcing entity types into rigid categories contradicts this at the architectural level.

5. **The count kept changing.** "14 domains" required constant recounting as entity types were added, split, or reclassified. Different documents disagreed on the count (3 Curriculum vs 4 Curriculum, 6 Activity vs 5 Activity + 1 Scheduling).

---

## Decision

**Replace the "14 domains in N categories" framing with "17 Entity Types with behavioral traits."**

Each entity type has its own identity, its own services, and its own graph relationships. Behavioral traits — not category membership — determine how an entity is handled.

### Entity Types (17)

Each entity type is a peer. No hierarchy of categories.

| EntityType | What It Is |
|------------|-----------|
| Task | Work to be done |
| Goal | Outcome to achieve |
| Habit | Behavior to build |
| Event | Time commitment to keep |
| Choice | Decision to make |
| Principle | Value to embody |
| Article | Teaching composition (essay-like narrative) |
| Ku | Atomic knowledge unit (concept, state, principle, substance) |
| Resource | Curated content (books, talks, films) |
| LearningStep | Step in a learning path |
| LearningPath | Ordered sequence of steps |
| Exercise | Instruction template for practicing curriculum |
| Submission | Student-uploaded work |
| Journal | Reflective writing (voice/text) |
| ActivityReport | Feedback about activity patterns over time |
| SubmissionReport | Assessment tied to a specific submission |
| LifePath | The user's life direction |

### Behavioral Traits (not categories)

Traits are properties of entity types that determine infrastructure behavior. An entity type *has* traits; it doesn't *belong to* a category.

| Trait | Method | What It Determines |
|-------|--------|--------------------|
| **Ownership** | `requires_user_uid()` | User-owned vs shared (admin-created) |
| **Content Origin** | `content_origin()` | Where content comes from (4 tiers: Curated, Curriculum, User-Created, Feedback) |
| **Processable** | `is_processable()` | Goes through a processing pipeline |
| **Derived** | `is_derived()` | Has parent in derivation chain |
| **Activity** | `is_activity()` | Shares Activity Domain infrastructure (factory, facade, sub-services) |

These methods already exist on `EntityType` in `entity_enums.py`. They are the architecture.

### The One Named Group: Activity

The 6 Activity entity types (Task, Goal, Habit, Event, Choice, Principle) genuinely share infrastructure — `create_common_sub_services()` factory, facade pattern, `create_activity_domain_route_config()`, `UserOwnedEntity` base class with identical access patterns. This grouping reflects shared code, not an imposed label.

### Everything Else: Peers Connected by Graph

All other entity types are peers. Their relationships to each other are expressed through graph edges:

```
(Article)-[:USES_KU]->(Ku)
(LearningStep)-[:TRAINS_KU]->(Ku)
(Exercise)-[:FOR_CURRICULUM]->(Article)
(Exercise)-[:FOR_GROUP]->(Group)
(Submission)-[:FULFILLS_EXERCISE]->(Exercise)
(Task)-[:APPLIES_KNOWLEDGE]->(Article|Ku)
(Entity)-[:SERVES_LIFE_PATH]->(LifePath)
```

These relationships — not category labels — define how entity types connect.

### What "Domain" Means Going Forward

"Domain" means: an entity type (or non-entity area like Finance or Groups) that has its own service facade, routes, and/or backend. It is a unit of code organization, not a taxonomic category. Ku is a domain. Exercise is a domain. Finance is a domain. They are peers, not members of categories.

---

## Alternatives Considered

### Alternative 1: Fix the Category Count

Recount and reassign categories to be consistent (e.g., "4 Curriculum" or "3 Curriculum + 1 Instruction").

**Why rejected:** This treats the symptom (inconsistent count) not the disease (imposed hierarchy). Every new entity type would require re-arguing which category it belongs to.

### Alternative 2: Formalize Categories as an Enum

Create a `DomainCategory` enum with values like `ACTIVITY`, `CURRICULUM`, `CONTENT`, etc.

**Why rejected:** This would codify the very hierarchy we're trying to eliminate. It adds code to maintain an abstraction that provides no behavioral value.

---

## Consequences

### Positive
- Entity types stand on their own — no forced categorization
- Aligns documentation with SKUEL's decentralization philosophy
- Eliminates recurring "how many domains?" counting debates
- New entity types don't require category assignment
- Graph relationships (not labels) define structure — consistent with Neo4j-native thinking

### Negative
- Significant documentation update required (~220 files reference the old framing)
- "14-Domain Architecture" was a recognizable shorthand — replacing it requires a new mental model
- Some developers may find the flat list of 17 entity types harder to navigate than categorized groups

### Neutral
- The `is_activity()`, `is_knowledge()`, etc. trait methods on EntityType remain — they're behavioral queries, not category assignments
- Type aliases (`ActivityEntity`, `CurriculumEntity`, etc.) in `entity_types.py` remain — they're type-narrowing tools, not taxonomic labels
- `NonKuDomain` enum (FINANCE, GROUP, CALENDAR, LEARNING) remains — it covers non-entity areas

---

## Implementation

### Phase 1: This ADR (current)
Establish the decision. No code changes.

### Phase 2: Documentation Update (future)
- Rename `FOURTEEN_DOMAIN_ARCHITECTURE.md` to `ENTITY_TYPE_ARCHITECTURE.md`
- Rewrite CLAUDE.md "14-Domain + 5-System Architecture" section
- Update EntityType docstring (replace 5-group framing with trait-based description)
- Update `entity_types.py` docstring
- Flatten `docs/domains/README.md` category structure
- Update ADRs, skills, pattern docs that reference domain categories
- Update Python docstrings that reference domain categories

### Key Files
- `core/models/enums/entity_enums.py` — EntityType enum + behavioral trait methods (already correct)
- `core/models/entity_types.py` — Type aliases (keep, they're type-narrowing tools)
- `docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md` — Primary rewrite target
- `CLAUDE.md` — Section rewrite

---

## Related

- ADR-046: Activity Domains Connect to Ku via Graph Edges
- ADR-041: Unified Ku Model
- `docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md`
