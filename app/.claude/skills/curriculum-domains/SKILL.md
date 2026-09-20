# Curriculum Domains Skill

> Use when building features for PathStep (PS), KU (atomic knowledge units), LP (Learning Paths), Exercise, or MOC (Maps of Content).

## When to Use This Skill

- Adding new features to any Curriculum Domain
- Understanding how Ku, PS, LP, Exercise differ from Activity Domains
- Implementing service methods for curriculum content
- Working with shared (non-user-owned) content
- Building learning path validation or adaptive sequencing
- Working with Ku organization (non-linear navigation, MOC-style)

## The 4 Curriculum Entity Types

> **PathStep IS knowledge. Exercise is APPLIED knowledge.** These four types form a
> hierarchy — not a flat peer group.

| Domain | UID Format | Topology | Role | Service |
|--------|-----------|----------|------|---------|
| **Ku** | `ku_{slug}_{random}` | Atom | Atomic knowledge unit (concept, state, principle, practice) | `KuService` |
| **PS (PathStep)** | `ps:{random}` | Unit | THE curriculum content entity — composed knowledge built on Kus | `PsService` |
| **LP (LearningPath)** | `lp:{random}` | Path | Organisational structure — sequences PathSteps | `LpService` |
| **Exercise** | varies | Instruction | Applied knowledge — instruction template anchored below PathStep | `ExerciseService` |

Exercise is **subordinate** to PathStep, not a peer structural pattern. `EntityType.EXERCISE.is_applied_knowledge()` → `True`; `EntityType.EXERCISE.is_curriculum_structure()` → `False`.

**Composition:** `(PathStep)-[:USES_KU]->(Ku)` — PathSteps compose atomic Kus into coherent learning content.
`(PathStep)-[:HAS_EXERCISE]->(Exercise)` — PathSteps anchor applied-knowledge instruction templates.
`(PathStep)-[:TRAINS_KU]->(Ku)` — PathSteps declare Kus as learning objectives.

**Note on "lesson":** there is no `Lesson` entity — PathStep IS the curriculum content entity. The string `"lesson"` is accepted by the ingestion detector (`TYPE_MAPPING` in `detector.py`) but is NOT in `_ENTITY_TYPE_ALIASES` — `EntityType.from_string("lesson")` returns `None`. Use `"ps"` or `"pathstep"` for DSL parsing; `"lesson"` is ingestion-only.

## World Layer vs User Layer

Curriculum entities are **World Layer** nodes — they exist independently of any user:

| Layer | Nodes |
|-------|-------|
| **World (shared, stable)** | Ku, PathStep, LearningPath, Exercise, Resource |
| **User (contextual, dynamic)** | UserEntry, EntryReport, and all Activity Domains |

The interaction edge between layers is where SKUEL's power emerges:
```cypher
(:User)-[:OWNS]->(:UserEntry)-[:FULFILLS_EXERCISE {revision}]->(:Exercise)<-[:HAS_EXERCISE]-(:PathStep)
```

See: `docs/architecture/ONTOLOGY_ARCHITECTURE.md`

## Key Difference from Activity Domains

**Curriculum content is SHARED, not user-owned:**

```python
# Activity Domains - user ownership
_user_ownership_relationship = "OWNS"  # Multi-tenant security

# Curriculum Domains - shared content
_user_ownership_relationship = None  # Global access
```

This means:
- No ownership verification on CRUD operations
- Content created by TEACHER+ roles, consumed by all
- User progress tracked via separate relationships (IN_PROGRESS, MASTERED, etc.)

## Architecture Overview

```
*Operations protocol        <- Contract (KuOperations, PsOperations, LpOperations)
        |
UniversalNeo4jBackend[T]     <- ONE instance per domain (no wrappers)
  + domain mixins            <- PsBackend (5 mixins), LpBackend (3 mixins), KuBackend (flat)
        |
        v
    {Domain}Service          <- Facade with explicit delegation methods
        |
        v
    Sub-services             <- core, search, intelligence, mastery, etc.
```

**Backend mixin decomposition:** PsBackend (71+ methods, 5 mixins), LpBackend (28 methods, 3 mixins: `_LpStepMixin`, `_LpProgressMixin`, `_LpIntelligenceMixin`), KuBackend (23 methods, flat — appropriate for atomic domain).

**Search service type narrowing (April 2026):** `PsSearchService` and `LpSearchService` are typed with domain-specific protocols (`PsOperations`, `LpOperations`) instead of generic `BackendOperations[T]`, giving them access to domain-specific backend methods.

## Service Sub-packages

| Domain | Sub-services | Location |
|--------|-------------|----------|
| **Ku** | `core`, `search`, `relationships`, `intelligence` | `core/services/ku/` |
| **PS** | `core`, `search`, `intelligence`, `mastery`, `organization`, `graph`, `context`, `semantic`, `practice`, `ai` | `core/services/ps/` |
| **LP** | `core`, `search`, `progress`, `ai` | `core/services/lp/` |

## Model Locations

| Domain | Directory | Model | DTO |
|--------|-----------|-------|-----|
| **Ku** | `core/models/ku/` | `ku.py` (extends Entity) | `ku_dto.py` |
| **PS** | `core/models/pathways/` | `path_step.py` (extends Curriculum) | `path_step_dto.py` |
| **LP** | `core/models/pathways/` | `learning_path.py` (extends Curriculum) | `learning_path_dto.py` |
| **Exercise** | `core/models/exercises/` | `exercise.py` (extends Curriculum) | `exercise_dto.py` |
| **Base** | `core/models/` | `curriculum.py` | `curriculum_dto.py` |

## Common Operations

### PathStep learning state
```python
# Record user view (implicit enrollment) — user first, then the step
await ps_service.mastery.record_view(user_uid, ps_uid)

# Mark in progress
await ps_service.mastery.mark_in_progress(user_uid, ps_uid)

# Get learning state for a user
state = await ps_service.mastery.get_learning_state(user_uid, ps_uid)
```

### Check path step readiness
```python
result = await ps_service.intelligence.is_ready(ps_uid, completed_step_uids)
```

### Validate learning path
```python
result = await lp_service.intelligence.validate_path_prerequisites(lp_uid)
```

### Organization (non-linear MOC navigation)
```python
# Behind the unauthenticated PathStep API: a PathStep subject (ps_core.get()) and
# shared-curriculum results only — a personal `moc: true` map is never read here.
# A PathStep → Ku or UserEntry-map edge is authored in the vault (`moc: true`).
await ps_service.organize(parent_ps_uid, child_ps_uid, order=1)
await ps_service.get_organized_children(parent_uid)
await ps_service.find_organizers(entity_uid)  # Multiple parents possible
```

### Ku domain classification (on the Ku, not a node)
A Ku's domain is an in-model property; there is no `:KnowledgeDomain` node.
Filter/facet on `nous` (L1 topic), `nous_subtopic`
(L2), and `sel_category` (SEL competency) — see `docs/patterns/NOUS_SUBTOPIC_FACET.md`.

## PS AI Sub-Service (FULL tier only)

The `.ai` sub-service is wired when `INTELLIGENCE_TIER=full`. Key methods:
- `suggest_step_applications(ps_uid)` — LLM categorized applications (tasks/habits/goals/real-world). Returns `StepApplicationsResult`.
- `suggest_learning_sequence(ps_uid, max_suggestions=5)` — prerequisite/next-step recommendations. Returns `StepLearningSequenceResult`.
- `search_by_semantic_query(query_text, limit, min_score)` — two-tier semantic/keyword search.
- `explain_step(ps_uid, target_level=...)` — 6 levels: beginner/intermediate/advanced/standard/brief/detailed.
- `suggest_practice_activities(ps_uid)` — JSON-based practice suggestions.

TypedDicts `StepApplicationsResult` and `StepLearningSequenceResult` are in `core/ports/query_types.py`.

## PathStep Reading & Learning State

PathSteps use **implicit enrollment** — no explicit signup step. Learning state progresses:

```
NONE → VIEWED → IN_PROGRESS → MASTERED
```

| State | Trigger | Relationship |
|-------|---------|-------------|
| VIEWED | Automatic on page load | `(User)-[:VIEWED]->(PathStep)` |
| IN_PROGRESS | User clicks "Start" | `(User)-[:IN_PROGRESS]->(PathStep)` |
| MASTERED | After exercise completion/teacher approval | `(User)-[:MASTERED]->(PathStep)` |

**Key routes:**
- `GET /path-steps` — Browse all PathSteps; rows link to the reading page, with an "Enrolled" badge on the session user's IN_PROGRESS steps
- `GET /explore/ps/{uid}` — Full reading page (markdown + TOC + learning objectives + actions)
- `POST /explore/ps/{uid}/progress` — the page's progress control (`state=learning|read`); `POST /api/path-steps/{uid}/start` is the HTMX fragment action that marks IN_PROGRESS (answers the updated button, not JSON)

**Contrast with Learning Paths:** LPs use **explicit enrollment** via `(User)-[:ENROLLED_IN]->(LearningPath)`.

## Note on MOC

MOC (Map of Content) is NOT a separate domain or EntityType. Any Entity with outgoing `ORGANIZES` relationships IS an organizer — a PathStep, a Ku, or a vault-authored UserEntry knowledge map (`moc: true`). The operations live on `PsService.organization` (`PsOrganizationService`) over the `_OrganizesMixin` backend — behind the unauthenticated PathStep API every read and the create take a PathStep subject (`ps_core.get()`) and return shared-curriculum entities only (`SHARED_CURRICULUM_TYPES`), so a personal `moc: true` map is never read through it; cross-entity edges come from vault ingestion and are read owner-verified on `/gradebook/{uid}`. `KuService` has no organization slot.

See: `core/services/ps/ps_organization_service.py` and `docs/domains/moc.md`

## Deep Dive Resources

**Architecture:**
- [ONTOLOGY_ARCHITECTURE.md](/docs/architecture/ONTOLOGY_ARCHITECTURE.md) - World/User layer design
- [CURRICULUM_GROUPING_PATTERNS.md](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md) - KU/PS/LP grouping patterns
- [ADR-023](/docs/decisions/ADR-023-curriculum-baseservice-migration.md) - Curriculum BaseService migration
- [ENTITY_TYPE_ARCHITECTURE.md](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md) - Complete domain architecture

**Patterns:**
- [OWNERSHIP_VERIFICATION.md](/docs/patterns/OWNERSHIP_VERIFICATION.md) - ContentScope.SHARED pattern

---

## Related Skills

- [activity-domains](../activity-domains/SKILL.md) - Contrast with user-owned domains
- [result-pattern](../result-pattern/SKILL.md) - All methods return `Result[T]`
- [neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md) - Graph queries
- [learning-loop](../learning-loop/SKILL.md) - Four-phase learning loop (Exercise → UserEntry → EntryReport → RevisedExercise)

## Related Documentation

- `/docs/architecture/ONTOLOGY_ARCHITECTURE.md` - World/User layer ontology
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` - Curriculum architecture
- `/docs/domains/moc.md` - MOC as emergent identity (ORGANIZES pattern)
