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
| `LessonApplicationDiscoveryService` | Reverse relationship queries (where is knowledge applied?) |
| `LessonContextService` | Context-first knowledge recommendations (*_for_user methods) |
| `LessonSemanticService` | Semantic relationship management |
| `LessonPracticeService` | Event-driven practice tracking |
| `LessonMasteryService` | Pedagogical tracking (VIEWED→IN_PROGRESS→MASTERED) |
| `LessonAdaptiveService` | Adaptive learning recommendations |
| `LessonOrganizationService` | ORGANIZES relationships — non-linear navigation (MOC pattern) |
| `LessonAiService` | AI-powered Lesson operations |
| `lesson_relationship_filters` | Relationship filtering utilities |

**Factory:** `create_lesson_sub_services()` - Specialized (handles circular core↔intelligence dependency)

**Unique Features:**
- **Substance tracking** - Measures how knowledge is LIVED (applied via Tasks, Habits, Events)
- **Per-user context** - `calculate_user_substance(lesson_uid, user_uid)` for personalized metrics
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

**Sub-services (4):** Created via `create_curriculum_sub_services("ku", ...)` — matches LS topology.

| Sub-service | Purpose |
|-------------|---------|
| `KuCoreService` | CRUD operations |
| `KuSearchService` | Text search, filtering |
| `UnifiedRelationshipService` | Graph relationship operations |
| `KuIntelligenceService` | Usage analysis, organization depth, graph analytics |

**Unique Features:**
- **Lightweight** - Extends Entity directly, not Curriculum
- **Composed into Lessons** - `(Lesson)-[:USES_KU]->(Ku)` relationship
- **Trained by LS** - `(Ls)-[:TRAINS_KU]->(Ku)` relationship
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

## LS (Learning Step) - The Edge

**Purpose:** A single step in a learning sequence — connects Lessons and Kus in meaningful order.

**Sub-services (5):**

| Sub-service | Purpose |
|-------------|---------|
| `LsCoreService` | CRUD operations (extends BaseService) |
| `LsSearchService` | Text search, filtering (extends BaseService) |
| `LsProgressService` | Progress tracking from Lesson completion (event-driven) |
| `LsIntelligenceService` | Readiness, practice analysis |
| `LsAiService` | AI-powered LS operations |

**Factory:** `create_curriculum_sub_services()` - Generic (simplest pattern). Progress sub-service created directly in `LsService.__init__()`.

**Backend:** `LsBackend` (extends `UniversalNeo4jBackend[LearningStep]`) — domain-specific methods: `get_steps_containing_lesson()`, `get_lesson_completion_progress()`.

**Unique Features:**
- **Event-driven progress** — `LsProgressService` subscribes to `LessonCompleted`, calculates LS progress from completed Lessons, publishes `LearningStepProgressUpdated` / `LearningStepCompleted`
- **HAS_LESSON relationship** — `(LS)-[:HAS_LESSON]->(Lesson)` connects steps to their lessons. Derived from shared KU references during migration.
- **Practice integration** - Links to Habits, Tasks, Events via relationships
- **Guidance relationships** - GUIDED_BY_PRINCIPLE, OFFERS_CHOICE
- **Prerequisite chains** - REQUIRES_STEP, TRAINS_KU

**Key Methods:**
```python
# Check if step is ready
await ls_service.intelligence.is_ready(ls_uid, completed_step_uids)

# Get practice summary (habits, tasks, events counts)
await ls_service.intelligence.get_practice_summary(ls_uid)

# Calculate guidance strength (principles 40% + choices 60%)
await ls_service.intelligence.calculate_guidance_strength(ls_uid)

# Practice completeness score (0.0-1.0)
await ls_service.intelligence.practice_completeness_score(ls_uid)
```

**Relationships Used:**
- `HAS_LESSON` - Step contains lesson (progress tracking)
- `REQUIRES_STEP` - Step prerequisites
- `TRAINS_KU` - Trains atomic knowledge units
- `BUILDS_HABIT`, `ASSIGNS_TASK`, `SCHEDULES_EVENT` - Practice integration
- `GUIDED_BY_PRINCIPLE`, `OFFERS_CHOICE` - Guidance

---

## LP (Learning Path) - The Path

**Purpose:** Complete learning sequence — the full staircase from start to mastery.

**Sub-services (5):**

| Sub-service | Purpose |
|-------------|---------|
| `LpCoreService` | CRUD operations (extends BaseService, requires LsService) |
| `LpSearchService` | Text search, filtering (extends BaseService) |
| `LpProgressService` | Progress tracking (event-driven) |
| `LpIntelligenceService` | Validation, analysis, adaptive, context (consolidated) |
| `LpAiService` | AI-powered LP operations |

**Factory:** `create_lp_sub_services()` - Specialized (requires cross-domain LsService dependency)

**Intelligence Location:** `LpIntelligenceService` lives at `core/services/lp_intelligence_service.py` (top level, NOT inside `lp/` directory) with a companion `lp_intelligence/` package for helpers.

**Unique Features:**
- **Cross-domain dependency** - LpCoreService requires LsService
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

| Feature | Lesson | KU | LS | LP |
|---------|---------|----|----|-----|
| **Sub-services** | 12 | 2 | 5 | 5 |
| **Factory** | Specialized | — | Generic | Specialized |
| **Extends** | Curriculum | Entity | Curriculum | Curriculum |
| **Complexity** | Highest | Lowest | Low | Medium |
| **User Progress** | Mastery level | — | Lesson completion | Enrollment |
| **Key Relationship** | USES_KU | (composed into Lesson) | HAS_LESSON, TRAINS_KU | CONTAINS_STEP |
| **Special Pattern** | Substance + Organization | Atomic reference | Practice + Progress | Validation |
| **Navigation** | Point lookup + non-linear | Referenced from Lessons | Sequential | Linear path |
| **Cross-Domain Dep** | None | None | None | LsService |
