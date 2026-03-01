# Curriculum Domain Specifics

> Special features and quirks for each Curriculum Domain.

## KU (Knowledge Unit) - The Point

**Purpose:** Atomic knowledge content — the single brick. `Ku` is the leaf class in the model hierarchy; `Curriculum` is the base.

**Sub-services (9):**

| Sub-service | Purpose |
|-------------|---------|
| `KuCoreService` | CRUD operations (extends BaseService) |
| `KuSearchService` | Text search, filtering (extends BaseService) |
| `KuGraphService` | Graph navigation and relationships |
| `KuSemanticService` | Semantic relationship management |
| `KuPracticeService` | Event-driven practice tracking |
| `KuInteractionService` | Pedagogical tracking (VIEWED→IN_PROGRESS→MASTERED) |
| `KuAdaptiveService` | Adaptive learning recommendations |
| `KuOrganizationService` | ORGANIZES relationships — non-linear navigation (MOC pattern) |
| `KuAiService` | AI-powered KU operations |

**Factory:** `create_ku_sub_services()` - Specialized (handles circular core↔intelligence dependency)

**Unique Features:**
- **Substance tracking** - Measures how knowledge is LIVED (applied via Tasks, Habits, Events)
- **Per-user context** - `calculate_user_substance(ku_uid, user_uid)` for personalized metrics
- **Semantic relationships** - REQUIRES_KNOWLEDGE, ENABLES, HAS_NARROWER, RELATED_TO
- **Content ingestion** - YAML frontmatter + Markdown body
- **Non-linear organization** - Any Ku can organize other Kus via ORGANIZES (emergent MOC pattern)

**Key Methods:**
```python
# Get KU with full context
await ku_service.intelligence.get_ku_with_context(uid)

# Calculate substance for user
await ku_service.intelligence.calculate_user_substance(ku_uid, user_uid)

# Non-linear organization (replaces old MOC service)
await ku_service.organize_ku(parent_uid, child_uid, order=1, importance="core")
await ku_service.get_subkus(parent_uid, depth=1)
await ku_service.get_parent_kus(ku_uid)  # Multiple parents possible!
await ku_service.is_organizer(ku_uid)
await ku_service.list_root_organizers()

# Find ready-to-learn knowledge
await ku_service.search.get_ready_to_learn(user_uid)

# Semantic neighborhood
await ku_service.semantic.get_semantic_neighborhood(ku_uid)
```

**UID Format:** `ku_{slug}_{random}` (flat, not hierarchical - ADR-013)

**MOC Pattern Note:** MOC is NOT an EntityType. Any Ku (or other Entity) "is" an organizer when it has outgoing ORGANIZES relationships. There is no separate `MocService` or `core/services/moc/` directory — this was dissolved into `KuOrganizationService`.

---

## LS (Learning Step) - The Edge

**Purpose:** A single step in a learning sequence — connects KUs in meaningful order.

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
- **Prerequisite chains** - REQUIRES_STEP, REQUIRES_KNOWLEDGE

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
- `REQUIRES_KNOWLEDGE` - Knowledge prerequisites
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

# Create path from KUs
await lp_service.create_path_from_knowledge_units(user_uid, name, ku_uids)
```

**Relationships:**
- `CONTAINS_STEP` - Path structure
- `ALIGNED_WITH_GOAL` - Goal alignment
- `HAS_MILESTONE_EVENT` - Milestone tracking
- `SERVES_LIFE_PATH` (incoming) - Life path designation

---

## Comparison Table

| Feature | KU | LS | LP |
|---------|----|----|-----|
| **Sub-services** | 9 | 4 | 5 |
| **Factory** | Specialized | Generic | Specialized |
| **Complexity** | Highest | Lowest | Medium |
| **User Progress** | Mastery level | Completion | Enrollment |
| **Key Relationship** | REQUIRES_KNOWLEDGE | REQUIRES_STEP | CONTAINS_STEP |
| **Special Pattern** | Substance + Organization | Practice | Validation |
| **Navigation** | Point lookup + non-linear | Sequential | Linear path |
| **Cross-Domain Dep** | None | None | LsService |
