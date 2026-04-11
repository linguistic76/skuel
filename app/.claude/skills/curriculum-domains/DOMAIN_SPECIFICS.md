# Curriculum Domain Specifics

> Special features and quirks for each Curriculum Domain.

## Lesson (Teaching Composition) - The Composition

**Purpose:** Essay-like teaching content that composes atomic Kus into narrative. `Lesson` extends `Curriculum` in the model hierarchy.

**Sub-services (12):**

| Sub-service | Purpose |
|-------------|---------|
| `LessonCoreService` | CRUD operations (extends BaseService) |
| `LessonSearchService` | Text search, filtering (extends BaseService) |
| `LessonGraphService` | Graph traversal, prerequisites, hub scores |
| `LessonApplicationDiscoveryService` | Reverse relationship queries via generic `find_activities_connected_to_knowledge()` |
| `LessonContextService` | Context-first knowledge recommendations (*_for_user methods) |
| `LessonSemanticService` | Semantic relationship management |
| `LessonPracticeService` | Event-driven practice tracking |
| `LessonMasteryService` | Pedagogical tracking (VIEWED→IN_PROGRESS→MASTERED) |
| `LessonAdaptiveService` | Adaptive learning recommendations |
| `LessonOrganizationService` | ORGANIZES relationships — non-linear navigation (MOC pattern) |
| `LessonAiService` | AI-powered Lesson operations |
| `lesson_relationship_filters` | Relationship filtering utilities |

**Factory:** `create_lesson_sub_services()` - Specialized (handles circular core↔intelligence dependency). All sub-services receive `LessonBackend` (as `repo` or `backend`) — no `neo4j_adapter` dependency. All Cypher lives on `LessonBackend` (59 methods total: 5 mixins — `_OrganizesMixin` (12), `_LearningStateMixin` (13), `_SemanticMixin` (11), `_KnowledgeContextMixin` (13), `_AdaptiveMixin` (10)).

**Unique Features:**
- **Substance tracking** - Measures how knowledge is LIVED across 6 channels: Tasks (0.05), Habits (0.10), Events (0.05), Choices (0.07), Principles (0.07), Journals (0.07 — deferred). All 6 channels wired into UserContext and `calculate_user_substance()`. YAML authoring creates structural edges via `connections.*` fields (e.g., `connections.applies_knowledge`, `connections.informed_by_knowledge`, `connections.grounded_in_knowledge`). See `/docs/guides/YAML_AUTHORING_GUIDE.md`.
- **Per-user context** - `calculate_user_substance(lesson_uid, user_context)` for personalized metrics
- **Semantic relationships** - REQUIRES_KNOWLEDGE, ENABLES, HAS_NARROWER, RELATED_TO
- **Content ingestion** - YAML frontmatter + Markdown body
- **Non-linear organization** - Any Lesson can organize other Lessons via ORGANIZES (emergent MOC pattern)
- **Composes atomic Kus** - `(Lesson)-[:USES_KU]->(Ku)` relationship

**Key Methods:**
```python
# Get Lesson with full context
await lesson_service.intelligence.get_lesson_with_context(uid)

# Calculate substance for user
await lesson_service.intelligence.calculate_user_substance(lesson_uid, user_uid)

# Non-linear organization (replaces old MOC service)
await lesson_service.organize(parent_uid, child_uid, order=1, importance="core")
await lesson_service.get_organized_children(parent_uid, depth=1)
await lesson_service.find_organizers(lesson_uid)  # Multiple parents possible!
await lesson_service.is_organizer(lesson_uid)
await lesson_service.list_root_organizers()

# Prev/next sibling navigation in MOC ORGANIZES order
# Returns KuNavigation(prev_uid, prev_title, next_uid, next_title)
# Propagates DB errors (not hidden); empty nav for legitimate empty states
await lesson_service.get_navigation(lesson_uid)

# Find ready-to-learn knowledge
await lesson_service.search.get_ready_to_learn(user_uid)

# Semantic neighborhood
await lesson_service.semantic.get_semantic_neighborhood(lesson_uid)
```

**UID Format:** `l_{slug}_{random}` (flat, not hierarchical - ADR-013)

**MOC Pattern Note:** MOC is NOT an EntityType. Any Lesson (or other Entity) "is" an organizer when it has outgoing ORGANIZES relationships. There is no separate `MocService` or `core/services/moc/` directory — this is managed by `LessonOrganizationService`.

---

## KU (Atomic Knowledge Unit) - The Atom

**Purpose:** Atomic knowledge unit — a single definable thing (concept, state, principle, substance, practice, value). `Ku` extends `Entity` directly (lightweight, like Resource).

**Sub-services (4):** Created via `create_curriculum_sub_services("ku", ...)` — matches PS topology.

| Sub-service | Purpose |
|-------------|---------|
| `KuCoreService` | CRUD operations |
| `KuSearchService` | Text search, filtering |
| `UnifiedRelationshipService` | Graph relationship operations |
| `KuIntelligenceService` | Usage analysis, organization depth, graph analytics |

**Unique Features:**
- **Lightweight** - Extends Entity directly, not Curriculum
- **Composed into Lessons** - `(Lesson)-[:USES_KU]->(Ku)` relationship
- **Trained by PS** - `(PS)-[:TRAINS_KU]->(Ku)` relationship
- **Namespace + category** - `ku_category` (KuCategory enum), `namespace`, `aliases`, `source`
- **SEL organization** - `sel_category` (SELCategory enum) classifies Kus by SEL competency. The `/ku` page shows a flat listing with bookmarks + latest sidebar (bookmarks via `UserRelationshipService` pin/unpin)
- **Reference node** - Ontology/reference, not a unit for learning

**Key Methods:**
```python
# Basic CRUD
await ku_service.core.create(...)
await ku_service.search.search(query)

# Find lessons that use this Ku
await ku_service.get_lessons(ku_uid)
```

**UID Format:** `ku_{slug}_{random}`

---

## PS (Path Step) - The Edge

**Purpose:** A single step in a learning sequence — connects Lessons and Kus in meaningful order.

**Sub-services (5):**

| Sub-service | Purpose |
|-------------|---------|
| `PsCoreService` | CRUD operations (extends BaseService) |
| `PsSearchService` | Text search, filtering (extends BaseService) |
| `PsProgressService` | Progress tracking from Lesson completion (event-driven) |
| `PsIntelligenceService` | Readiness, practice analysis |
| `PsAiService` | AI-powered PS operations |

**Factory:** `create_curriculum_sub_services()` - Generic (simplest pattern). Progress sub-service created directly in `PsService.__init__()`.

**Backend:** `PsBackend` (extends `UniversalNeo4jBackend[PathStep]`) — domain-specific methods: `get_steps_containing_lesson()`, `get_lesson_completion_progress()`.

**Unique Features:**
- **Event-driven progress** — `PsProgressService` subscribes to `LessonCompleted`, calculates PS progress from completed Lessons, publishes `PathStepProgressUpdated` / `PathStepCompleted`
- **HAS_LESSON relationship** — `(PS)-[:HAS_LESSON]->(Lesson)` connects steps to their lessons. Derived from shared KU references during migration.
- **Practice integration** - Links to Habits, Tasks, Events via relationships
- **Guidance relationships** - GUIDED_BY_PRINCIPLE, INFORMS_CHOICE
- **Prerequisite chains** - REQUIRES_STEP, TRAINS_KU

**Key Methods:**
```python
# Check if step is ready
await ps_service.intelligence.is_ready(ps_uid, completed_step_uids)

# Get practice summary (habits, tasks, events counts)
await ps_service.intelligence.get_practice_summary(ps_uid)

# Calculate guidance strength (principles 40% + choices 60%)
await ps_service.intelligence.calculate_guidance_strength(ps_uid)

# Practice completeness score (0.0-1.0)
await ps_service.intelligence.practice_completeness_score(ps_uid)
```

**Relationships Used:**
- `HAS_LESSON` - Step contains lesson (activity domains inherited via this traversal)
- `REQUIRES_STEP` - Step prerequisites
- `TRAINS_KU` - Trains atomic knowledge units
- Practice and guidance relationships live on **Lessons**, not PS. PS inherits via `(PS)-[:HAS_LESSON]->(Lesson)-[:rel]->(Activity)`:
  - `BUILDS_HABIT`, `ASSIGNS_TASK`, `SCHEDULES_EVENT` - Practice integration (on Lesson)
  - `SUPPORTS_GOAL` - Goal alignment (on Lesson)
  - `GUIDED_BY_PRINCIPLE`, `INFORMS_CHOICE` - Guidance (on Lesson)

---

## LP (Learning Path) - The Path

**Purpose:** Complete learning sequence — the full staircase from start to mastery.

**Sub-services (5):**

| Sub-service | Purpose |
|-------------|---------|
| `LpCoreService` | CRUD operations (extends BaseService, requires PsService) |
| `LpSearchService` | Text search, filtering (extends BaseService) |
| `LpProgressService` | Progress tracking (event-driven) |
| `LpIntelligenceService` | Validation, analysis, adaptive, context (consolidated) |
| `LpAiService` | AI-powered LP operations |

**Factory:** `create_lp_sub_services()` - Specialized (requires cross-domain PsService dependency)

**Intelligence Location:** `LpIntelligenceService` lives at `core/services/lp/lp_intelligence_service.py` (inside the `lp/` package, exported via `lp/__init__.py`).

**Unique Features:**
- **Cross-domain dependency** - LpCoreService requires PsService
- **Validation** - Ensures prerequisite chains are valid
- **Adaptive sequencing** - Personalizes step order based on user progress
- **Goal alignment** - ALIGNED_WITH_GOAL relationship
- **Milestone tracking** - HAS_MILESTONE_EVENT relationship
- **Life path destination** - Can be designated as user's ULTIMATE_PATH

**Key Methods:**
```python
# Validate learning path prerequisites
await lp_service.intelligence.validate_path_prerequisites(lp_uid)

# Get adaptive sequence for user
await lp_service.intelligence.get_adaptive_sequence(lp_uid, user_uid)

# Identify blockers
await lp_service.intelligence.identify_path_blockers(lp_uid, user_uid)

# Get optimal path recommendation
await lp_service.intelligence.get_optimal_path_recommendation(user_uid, goal_uid)

# Create path from Lessons
await lp_service.create_path_from_lessons(user_uid, name, lesson_uids)
```

**Relationships:**
- `CONTAINS_STEP` - Path structure
- `ALIGNED_WITH_GOAL` - Goal alignment
- `HAS_MILESTONE_EVENT` - Milestone tracking
- `SERVES_LIFE_PATH` (incoming) - Life path designation

---

## Comparison Table

| Feature | Lesson | KU | PS | LP |
|---------|---------|----|----|-----|
| **Sub-services** | 12 | 2 | 5 | 5 |
| **Factory** | Specialized | — | Generic | Specialized |
| **Extends** | Curriculum | Entity | Curriculum | Curriculum |
| **Complexity** | Highest | Lowest | Low | Medium |
| **User Progress** | Mastery level | — | Lesson completion | Enrollment |
| **Key Relationship** | USES_KU | (composed into Lesson) | HAS_LESSON, TRAINS_KU | CONTAINS_STEP |
| **Special Pattern** | Substance + Organization | Atomic reference | Practice + Progress | Validation |
| **Navigation** | Point lookup + non-linear | Referenced from Lessons | Sequential | Linear path |
| **Cross-Domain Dep** | None | None | None | PsService |
