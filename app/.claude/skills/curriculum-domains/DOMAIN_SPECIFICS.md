# Curriculum Domain Specifics

> Special features and quirks for each Curriculum Domain.

## KU (Knowledge Unit) - The Point

**Purpose:** Atomic knowledge content - a single brick in the knowledge building.

**Sub-services (8):**

| Sub-service | Purpose |
|-------------|---------|
| `KuCoreService` | CRUD operations (extends BaseService) |
| `KuSearchService` | Text search, filtering (extends BaseService) |
| `KuGraphService` | Graph navigation and relationships |
| `KuSemanticService` | Semantic relationship management |
| `KuPracticeService` | Event-driven practice tracking |
| `KuInteractionService` | Pedagogical tracking (VIEWED→IN_PROGRESS→MASTERED) |
| `UnifiedRelationshipService` | Harmonious relationship operations |
| `KuIntelligenceService` | Intelligence and analytics (extends BaseIntelligenceService) |

**Factory:** `create_ku_sub_services()` - Specialized (handles circular core↔intelligence dependency)

**Unique Features:**
- **Substance tracking** - Measures how knowledge is LIVED (applied via Tasks, Habits, Events)
- **Per-user context** - `calculate_user_substance(ku_uid, user_uid)` for personalized metrics
- **Semantic relationships** - REQUIRES_KNOWLEDGE, ENABLES, HAS_NARROWER, RELATED_TO
- **Content ingestion** - YAML frontmatter + Markdown body
- **Circular dependency** - Intelligence created BEFORE core (core depends on intelligence)

**Key Methods:**
```python
# Get KU with full context
await ku_service.intelligence.get_ku_with_context(uid)

# Calculate substance for user
await ku_service.intelligence.calculate_user_substance(ku_uid, user_uid)

# Find ready-to-learn knowledge
await ku_service.search.get_ready_to_learn(user_uid)

# Semantic neighborhood
await ku_service.semantic.get_semantic_neighborhood(ku_uid)
```

**UID Format:** `ku.{filename}` (flat, not hierarchical - ADR-013)

---

## LS (Learning Step) - The Edge

**Purpose:** A single step in a learning sequence - connects KUs in meaningful order.

**Sub-services (4 - minimal design):**

| Sub-service | Purpose |
|-------------|---------|
| `LsCoreService` | CRUD operations (extends BaseService) |
| `LsSearchService` | Text search, filtering (extends BaseService) |
| `UnifiedRelationshipService` | Step connections |
| `LsIntelligenceService` | Readiness, practice analysis (extends BaseIntelligenceService) |

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

**Purpose:** Complete learning sequence - the full staircase from start to mastery.

**Sub-services (5):**

| Sub-service | Purpose |
|-------------|---------|
| `LpCoreService` | CRUD operations (extends BaseService, requires LsService) |
| `LpSearchService` | Text search, filtering (extends BaseService) |
| `UnifiedRelationshipService` | Path-step associations |
| `LpProgressService` | Progress tracking (event-driven) |
| `LpIntelligenceService` | Validation, analysis, adaptive, context (consolidated) |

**Factory:** `create_lp_sub_services()` - Specialized (requires cross-domain LsService dependency)

**January 2026 Consolidation:**
`LpIntelligenceService` now handles ALL intelligence operations (validation, analysis, adaptive, context). Four separate services were deleted and consolidated:
- Was: LpValidationService, LpAnalysisService, LpAdaptiveService, LpContextService
- Now: Single `LpIntelligenceService` (extends BaseIntelligenceService)

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

## MOC (Map of Content) - The Graph

**Purpose:** Non-linear navigation - a map of the knowledge building, not a path through it.

**Sub-services (8 - manual creation due to circular deps):**

| Sub-service | Purpose |
|-------------|---------|
| `MocCoreService` | CRUD + template operations (extends BaseService) |
| `MocSectionService` | Section hierarchy management (circular with core) |
| `MocContentService` | Content aggregation |
| `MocDiscoveryService` | Search, discovery, recommendations |
| `MocSearchService` | Search operations (extends BaseService) |
| `MocIntelligenceService` | Intelligence (extends BaseIntelligenceService) |
| `UnifiedRelationshipService` (MOC) | MOC relationships |
| `UnifiedRelationshipService` (Section) | Section relationships |

**Creation:** **Manual** in `MocService.__init__()` - Cannot use factory due to circular dependencies

**Unique Features:**
- **Post-init wiring** - Circular dependency between core ↔ section services
- **Dual relationship services** - One for MOC, one for MOCSection
- **Hierarchical sections** - Nested subsections with KU references
- **Cross-domain bridges** - BRIDGES_TO relationship connects related MOCs
- **Multi-content aggregation** - Contains KUs, LPs, AND Principles

**Key Methods:**
```python
# Get navigation suggestions
await moc_service.intelligence.suggest_navigation(moc_uid, user_context)

# Calculate coverage metrics
await moc_service.intelligence.calculate_coverage(moc_uid)

# Find bridge opportunities
await moc_service.intelligence.find_bridge_candidates(moc_uid)

# Add section
await moc_service.section.add_section(moc_uid, title, content)

# Create from template
await moc_service.core.create_from_template(template_uid, user_uid)
```

**Circular Dependency Resolution:**
```python
class MocService:
    def __init__(self, backend, driver, graph_intel, event_bus):
        # Step 1: Create section WITHOUT core reference
        self.section = MocSectionService(
            backend=backend, driver=driver,
            core_service=None,  # Will be wired later
            section_relationships=self.section_relationships,
        )

        # Step 2: Create core WITH section reference
        self.core = MocCoreService(
            backend=backend, driver=driver,
            section_service=self.section,
            event_bus=event_bus,
        )

        # Step 3: Wire core back to section
        self.section.core_service = self.core
```

**Relationships:**
- `CONTAINS_PATH` - Contains Learning Paths
- `CONTAINS_PRINCIPLE` - Contains Principles
- `BRIDGES_TO` - Connects to related MOCs
- `HAS_SECTION` - Hierarchical structure

---

## Comparison Table

| Feature | KU | LS | LP | MOC |
|---------|----|----|----|----|
| **Sub-services** | 8 | 4 | 5 | 8 |
| **Factory** | Specialized | Generic | Specialized | Manual |
| **Complexity** | Highest | Lowest | Medium | High |
| **User Progress** | Mastery level | Completion | Enrollment | Bookmarks |
| **Key Relationship** | REQUIRES_KNOWLEDGE | REQUIRES_STEP | CONTAINS_STEP | CONTAINS_PATH |
| **Special Pattern** | Substance | Practice | Validation | Post-init |
| **Navigation** | Point lookup | Sequential | Linear path | Non-linear |
| **Circular Dep** | Core↔Intel | None | None | Core↔Section |
| **Cross-Domain Dep** | None | None | LsService | None |
