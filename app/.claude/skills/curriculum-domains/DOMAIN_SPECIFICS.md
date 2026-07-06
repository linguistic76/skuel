# Curriculum Domain Specifics

> Special features and quirks for each Curriculum Domain.

## PS (PathStep) — THE Curriculum Content Entity

**Purpose:** THE curriculum content entity. Composes atomic Kus into coherent learning content and sits within a LearningPath. `PathStep` extends `Curriculum` in the model hierarchy. (2026-04: the former `Lesson` entity was merged into `PathStep` — PathStep absorbed all Lesson capabilities.)

**Sub-services (12):** Created via the specialized factory `create_ps_sub_services()` (`core/services/curriculum_domain_config.py`).

| Sub-service | Purpose |
|-------------|---------|
| `PsCoreService` | CRUD operations + persistence (extends BaseService) |
| `PsSearchService` | Text search, filtering (extends BaseService) |
| `PsGraphService` | Graph traversal, prerequisites, hub scores |
| `PsSemanticService` | Semantic relationship management |
| `PsPracticeService` | Event-driven practice tracking |
| `PsMasteryService` | Pedagogical tracking (VIEWED → IN_PROGRESS → MASTERED) |
| `PsAdaptiveService` | Adaptive learning recommendations |
| `PsApplicationDiscoveryService` | Reverse relationship queries via generic `find_activities_connected_to_knowledge()` |
| `PsContextService` | Context-first knowledge recommendations (`*_for_user` methods) |
| `PsOrganizationService` | `ORGANIZES` relationships — non-linear navigation (MOC pattern) |
| `PsIntelligenceService` | Readiness assessment, practice analysis, substance |
| `PsProgressService` | KU completion progress (event-driven) |

Plus optional `PsAiService` (FULL tier only — LLM / embedding features).

**Factory:** `create_ps_sub_services()` — specialized (handles circular core ↔ intelligence dependency, creates intelligence BEFORE core). All sub-services receive `PsBackend` (as `repo` or `backend`) — no `neo4j_adapter` dependency. All Cypher lives on `PsBackend`, decomposed into 5 domain-specific mixins: `_OrganizesMixin`, `_LearningStateMixin`, `_SemanticMixin`, `_KnowledgeContextMixin`, `_AdaptiveMixin`.

**Unique Features:**
- **Substance tracking** — measures how knowledge is LIVED. Two tiers:

  | Channel | Weight | How to declare |
  |---------|--------|----------------|
  | Tasks | 0.05 | `connections.assigns_task` in PathStep YAML |
  | Habits | 0.10 | `connections.builds_habit` in PathStep YAML |
  | Events | 0.05 | `connections.schedules_event` in PathStep YAML |
  | Choices | 0.07 | `connections.informs_choice` in PathStep YAML |
  | Principles | 0.07 | `connections.guided_by_principle` in PathStep YAML |
  | UserEntry | 0.07 | **Pipeline-driven — cannot be YAML-declared.** Accrues at submission time when a user submits a UserEntry that `FULFILLS_EXERCISE` for this PathStep. |

  The 5 `connections.*` YAML fields create structural edges at ingestion time. UserEntry substance accrues at runtime via the `EXTRACT_ACTIVITIES` pipeline (ADR-069) — you cannot pre-declare what a user will write. Do not look for a `connections.reflects_knowledge` field; it does not exist. See `/docs/guides/YAML_AUTHORING_GUIDE.md`.
- **Per-user context** — `calculate_user_substance(ps_uid, user_context)` for personalized metrics.
- **Semantic relationships** — REQUIRES_KNOWLEDGE, ENABLES, HAS_NARROWER, RELATED_TO.
- **Content ingestion** — YAML frontmatter + Markdown body.
- **Non-linear organization** — any PathStep can organize other PathSteps via `ORGANIZES` (emergent MOC pattern).
- **Composes atomic Kus** — `(PathStep)-[:USES_KU]->(Ku)` relationship.
- **Learning-state tracking** — `VIEWED` / `IN_PROGRESS` / `MASTERED` / `BOOKMARKED` / `MARKED_AS_READ` user-owned edges.

**Key Methods:**
```python
# Get PathStep with full context
await ps_service.intelligence.get_ps_with_context(uid)

# Calculate substance for user
await ps_service.intelligence.calculate_user_substance(ps_uid, user_uid)

# Non-linear organization (MOC pattern)
await ps_service.organization.organize(parent_uid, child_uid, order=1, importance="core")
await ps_service.organization.get_organized_children(parent_uid, depth=1)
await ps_service.organization.find_organizers(ps_uid)   # Multiple parents possible
await ps_service.organization.is_organizer(ps_uid)
await ps_service.organization.list_root_organizers()

# Prev/next sibling navigation in MOC ORGANIZES order
await ps_service.organization.get_navigation(ps_uid)

# Readiness and practice
await ps_service.intelligence.is_ready(ps_uid, completed_uids)
await ps_service.intelligence.get_practice_summary(ps_uid)

# Adaptive recommendations
await ps_service.adaptive.get_recommendations(user_uid)

# Semantic neighborhood
await ps_service.semantic.get_semantic_neighborhood(ps_uid)

# Progress (event-driven KU completion)
await ps_service.progress.record_completion(ps_uid, user_uid)
```

**UID Format:** `ps:{namespace}:{slug}` (e.g., `ps:core:meditation-basics`).

**MOC Pattern Note:** MOC is NOT an EntityType. Any PathStep (or other Entity) "is" an organizer when it has outgoing `ORGANIZES` relationships. There is no separate `MocService` or `core/services/moc/` directory — this is managed by `PsOrganizationService`.

---

## KU (Atomic Knowledge Unit) — The Atom

**Purpose:** Atomic knowledge unit — a single definable thing (concept, state, principle, substance, practice, value). `Ku` extends `Entity` directly (lightweight, like Resource).

**Sub-services (4):** Created via `create_curriculum_sub_services("ku", ...)`.

| Sub-service | Purpose |
|-------------|---------|
| `KuCoreService` | CRUD operations |
| `KuSearchService` | Text search, filtering |
| `UnifiedRelationshipService` | Graph relationship operations |
| `KuIntelligenceService` | Usage analysis, organization depth, graph analytics |

**Unique Features:**
- **Lightweight** — extends Entity directly, not Curriculum.
- **Composed into PathSteps** — `(PathStep)-[:USES_KU]->(Ku)` relationship.
- **Trained by PathSteps** — `(PathStep)-[:TRAINS_KU]->(Ku)` relationship.
- **Aliases + NOUS topics** — `aliases` (alternative names), `nous` (NOUS topic membership — the category vocabulary), `sel_category` (SELCategory enum). The former `namespace`/`ku_category`/`source` fields were retired 2026-07-06.
- **SEL organization** — `sel_category` (SELCategory enum) classifies Kus by SEL competency. The `/ku` page shows a flat listing with bookmarks + latest sidebar.
- **Reference node** — ontology/reference, not a unit for learning.

**Key Methods:**
```python
# Basic CRUD
await ku_service.core.create(...)
await ku_service.search.search(query)

# Find PathSteps that use this Ku
await ku_service.get_path_steps(ku_uid)
```

**UID Format:** `ku_{slug}_{random}`.

---

## LP (LearningPath) — The Path

**Purpose:** A complete, ordered sequence of PathSteps — the full staircase from start to mastery.

**Sub-services (5):**

| Sub-service | Purpose |
|-------------|---------|
| `LpCoreService` | CRUD + HAS_STEP management (extends BaseService, requires PsService) |
| `LpSearchService` | Text search, filtering (extends BaseService) |
| `LpProgressService` | Mastery progress (event-driven) |
| `LpIntelligenceService` | Validation, analysis, adaptive step, context |
| `LpAiService` | Optional LLM features (FULL tier) |

**Factory:** `create_lp_sub_services()` — specialized (requires cross-domain `PsService` dependency). No `executor` parameter — all Cypher delegated to `LpBackend`.

**Backend:** `LpBackend` (3 domain-specific mixins): `_lp_step_mixin` (step management + path CRUD), `_lp_progress_mixin` (KU mastery + search queries), `_lp_intelligence_mixin` (intelligence + adaptive learning).

**Unique Features:**
- **Cross-domain dependency** — `LpCoreService` requires `PsService`.
- **Validation** — ensures prerequisite chains are valid.
- **Adaptive sequencing** — personalizes step order based on user progress.
- **Goal alignment** — `ALIGNED_WITH_GOAL` relationship.
- **Milestone tracking** — `HAS_MILESTONE_EVENT` relationship.
- **Life path destination** — can be designated as user's `SERVES_LIFE_PATH`.

**Key Methods:**
```python
# Validate learning path prerequisites
await lp_service.intelligence.validate_path_prerequisites(lp_uid)

# Get next adaptive step for user
await lp_service.intelligence.get_next_adaptive_step(step_uid, user_uid)

# Identify blockers
await lp_service.intelligence.identify_path_blockers(lp_uid, user_uid)

# Get optimal path recommendation
await lp_service.intelligence.get_optimal_path_recommendation(user_uid, goal_domain)

# Create path from PathSteps
await lp_service.create_path_from_steps(user_uid, name, ps_uids)
```

**Relationships:**
- `HAS_STEP` — path structure (ordered).
- `ALIGNED_WITH_GOAL` — goal alignment.
- `HAS_MILESTONE_EVENT` — milestone tracking.
- `SERVES_LIFE_PATH` (incoming) — life path designation.

**UID Format:** `lp:{namespace}:{slug}`.

---

## Exercise — The Learning Loop Anchor

**Purpose:** The instruction template that closes the learning loop. Without Exercise, the loop (Exercise → UserEntry → EntryReport → RevisedExercise) cannot start. Exercise is a first-class curriculum EntityType — architecturally coequal with PathStep, not an appendage.

**Four scopes:**

| Scope | Who creates | Anchor | Requirement |
|-------|-------------|--------|-------------|
| `PERSONAL` | Any user | `path_step_uid` optional | When set, writes `Exercise.path_step_uid` **and** `(PathStep)-[:HAS_EXERCISE]->(Exercise)` (dual-write); unset = free-standing template in the user's library |
| `ASSIGNED` | TEACHER+ | `group_uid` required | Shared via `SHARED_WITH_GROUP` (ADR-040) |
| `ASSESSMENT` | TEACHER+ | `scoring_rubric` required | `pass_threshold` defaults to 0.7 |
| `CURRICULUM` | Content vault (ingestion only) | `exercise_uids:` in PathStep YAML | Shared content, no user OWNS edge; API create rejected; ingestion rejects every other scope (no owner mechanism at the file boundary) |

**Service:** `ExerciseService` — flat (no sub-service decomposition). CRUD plus domain-specific methods:
- `create_exercise(user_uid, name, instructions, ..., path_step_uid)` — convenience builder
- `create(entity: Exercise)` — canonical creation with all side effects (OWNS + HAS_EXERCISE + sharing)
- `link_to_path_step(exercise_uid, path_step_uid)` — write/repair `HAS_EXERCISE` edge
- `link_to_curriculum(exercise_uid, curriculum_uid)` — REQUIRES_KNOWLEDGE to Ku/Resource
- `get_required_knowledge(exercise_uid)` — all Kus required by this exercise
- `get_exercises_for_curriculum(curriculum_uid)` — reverse lookup

**Key Relationships:**
- `(PathStep)-[:HAS_EXERCISE]->(Exercise)` — curriculum anchor (anchored PERSONAL + CURRICULUM scopes)
- `(User)-[:OWNS]->(Exercise)` — creator ownership
- `(Exercise)-[:SHARED_WITH_GROUP]->(Group)` — ASSIGNED scope distribution
- `(Exercise)-[:REQUIRES_KNOWLEDGE]->(Ku)` — declared prerequisites
- `(UserEntry)-[:FULFILLS_EXERCISE]->(Exercise)` — user work linkage (incoming)

**UID Format:** `ex_{slug}_{hash}` (via `UIDGenerator.generate_uid("ex", name)`).

**Creation via CRUD factory:** `ExerciseCreateRequest` is registered in `ConversionServiceV2.CONVERTER_REGISTRY`. Route: `POST /api/exercises/create` (TEACHER+ role required). `ExerciseService.create()` handles all relationship writes after the node is persisted.

---

## Comparison Table

| Feature | PS (PathStep) | KU | LP | Exercise |
|---------|---------------|----|-----|---------|
| **Sub-services** | 12 (+ optional `ai`) | 4 | 5 | 1 (flat) |
| **Factory** | Specialized (`create_ps_sub_services`) | Generic (`create_curriculum_sub_services`) | Specialized (`create_lp_sub_services`) | Generic (`BaseService`) |
| **Extends** | Curriculum | Entity | Curriculum | Curriculum |
| **Complexity** | Highest | Lowest | Medium | Low |
| **User Progress** | Learning state (VIEWED / IN_PROGRESS / MASTERED) | — (bookmark only) | Enrollment + mastery | `FULFILLS_EXERCISE` submission tracking |
| **Key Relationship** | `USES_KU`, `HAS_STEP` (incoming) | (composed into PS) | `HAS_STEP` | `HAS_EXERCISE` ← PathStep, `REQUIRES_KNOWLEDGE` → Ku |
| **Special Pattern** | Substance + Organization + Activity integration | Atomic reference | Validation + adaptive | Three-scope model + learning loop anchor |
| **Navigation** | Point lookup + non-linear (ORGANIZES) | Referenced from PathSteps | Linear path | Anchored to PathStep (PERSONAL) or Group (ASSIGNED) |
| **Cross-Domain Dep** | None | None | PsService | None |

**Activity integration lives directly on PathSteps** (no intermediate Lesson node — 2026-04 merge):
`BUILDS_HABIT`, `ASSIGNS_TASK`, `SCHEDULES_EVENT`, `SUPPORTS_GOAL`, `GUIDED_BY_PRINCIPLE`, `INFORMS_CHOICE`.
