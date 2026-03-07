# Curriculum Domain Specifics

> Special features and quirks for each Curriculum Domain.

## Article (Teaching Composition) - The Composition

**Purpose:** Essay-like teaching content that composes atomic Kus into narrative. `Article` extends `Curriculum` in the model hierarchy.

**Sub-services (10):**

| Sub-service | Purpose |
|-------------|---------|
| `ArticleCoreService` | CRUD operations (extends BaseService) |
| `ArticleSearchService` | Text search, filtering (extends BaseService) |
| `ArticleGraphService` | Graph navigation and relationships |
| `ArticleSemanticService` | Semantic relationship management |
| `ArticlePracticeService` | Event-driven practice tracking |
| `ArticleMasteryService` | Pedagogical tracking (VIEWED→IN_PROGRESS→MASTERED) |
| `ArticleAdaptiveService` | Adaptive learning recommendations |
| `ArticleOrganizationService` | ORGANIZES relationships — non-linear navigation (MOC pattern) |
| `ArticleAiService` | AI-powered Article operations |
| `ArticleRelationshipHelpers` | Relationship filtering utilities |

**Factory:** `create_article_sub_services()` - Specialized (handles circular core↔intelligence dependency)

**Unique Features:**
- **Substance tracking** - Measures how knowledge is LIVED (applied via Tasks, Habits, Events)
- **Per-user context** - `calculate_user_substance(article_uid, user_uid)` for personalized metrics
- **Semantic relationships** - REQUIRES_KNOWLEDGE, ENABLES, HAS_NARROWER, RELATED_TO
- **Content ingestion** - YAML frontmatter + Markdown body
- **Non-linear organization** - Any Article can organize other Articles via ORGANIZES (emergent MOC pattern)
- **Composes atomic Kus** - `(Article)-[:USES_KU]->(Ku)` relationship

**Key Methods:**
```python
# Get Article with full context
await article_service.intelligence.get_article_with_context(uid)

# Calculate substance for user
await article_service.intelligence.calculate_user_substance(article_uid, user_uid)

# Non-linear organization (replaces old MOC service)
await article_service.organize_article(parent_uid, child_uid, order=1, importance="core")
await article_service.get_organized_children(parent_uid, depth=1)
await article_service.get_parent_articles(article_uid)  # Multiple parents possible!
await article_service.is_organizer(article_uid)
await article_service.list_root_organizers()

# Find ready-to-learn knowledge
await article_service.search.get_ready_to_learn(user_uid)

# Semantic neighborhood
await article_service.semantic.get_semantic_neighborhood(article_uid)
```

**UID Format:** `a_{slug}_{random}` (flat, not hierarchical - ADR-013)

**MOC Pattern Note:** MOC is NOT an EntityType. Any Article (or other Entity) "is" an organizer when it has outgoing ORGANIZES relationships. There is no separate `MocService` or `core/services/moc/` directory — this is managed by `ArticleOrganizationService`.

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
- **Composed into Articles** - `(Article)-[:USES_KU]->(Ku)` relationship
- **Trained by LS** - `(Ls)-[:TRAINS_KU]->(Ku)` relationship
- **Namespace + category** - `ku_category` (KuCategory enum), `namespace`, `aliases`, `source`
- **Reference node** - Ontology/reference, not essay-like teaching content

**Key Methods:**
```python
# Basic CRUD
await ku_service.core.create(...)
await ku_service.search.search(query)

# Find articles that use this Ku
await ku_service.get_articles_using(ku_uid)
```

**UID Format:** `ku_{slug}_{random}`

---

## LS (Learning Step) - The Edge

**Purpose:** A single step in a learning sequence — connects Articles and Kus in meaningful order.

**Sub-services (4 - minimal design):**

| Sub-service | Purpose |
|-------------|---------|
| `LsCoreService` | CRUD operations (extends BaseService) |
| `LsSearchService` | Text search, filtering (extends BaseService) |
| `LsIntelligenceService` | Readiness, practice analysis |
| `LsAiService` | AI-powered LS operations |

**Factory:** `create_curriculum_sub_services()` - Generic (simplest pattern)

**Unique Features:**
- **Minimal design** - Intentionally simple, delegates complexity to LP
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

# Create path from Articles
await lp_service.create_path_from_articles(user_uid, name, article_uids)
```

**Relationships:**
- `CONTAINS_STEP` - Path structure
- `ALIGNED_WITH_GOAL` - Goal alignment
- `HAS_MILESTONE_EVENT` - Milestone tracking
- `SERVES_LIFE_PATH` (incoming) - Life path designation

---

## Comparison Table

| Feature | Article | KU | LS | LP |
|---------|---------|----|----|-----|
| **Sub-services** | 10 | 2 | 4 | 5 |
| **Factory** | Specialized | — | Generic | Specialized |
| **Extends** | Curriculum | Entity | Curriculum | Curriculum |
| **Complexity** | Highest | Lowest | Low | Medium |
| **User Progress** | Mastery level | — | Completion | Enrollment |
| **Key Relationship** | USES_KU | (composed into Article) | TRAINS_KU | CONTAINS_STEP |
| **Special Pattern** | Substance + Organization | Atomic reference | Practice | Validation |
| **Navigation** | Point lookup + non-linear | Referenced from Articles | Sequential | Linear path |
| **Cross-Domain Dep** | None | None | None | LsService |
