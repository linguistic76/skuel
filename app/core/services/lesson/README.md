# Lesson Sub-Services Architecture

This directory contains modular sub-services for Lesson (unit for learning) operations following the **Facade Pattern**.

## Architecture Overview

```
/core/services/
├── lesson/                                # Domain sub-services (THIS DIRECTORY)
│   ├── lesson_core_service.py             # CRUD operations
│   ├── lesson_search_service.py           # Search and discovery
│   ├── lesson_graph_service.py            # Graph traversal, prerequisites
│   ├── lesson_semantic_service.py         # Semantic relationships
│   ├── lesson_mastery_service.py          # Pedagogical state tracking
│   ├── lesson_practice_service.py         # Event-driven practice tracking
│   ├── lesson_ai_service.py              # Optional AI features
│   ├── lesson_adaptive_service.py        # Adaptive learning recommendations
│   ├── lesson_application_discovery_service.py  # Reverse relationship queries
│   ├── lesson_context_service.py        # Context-first knowledge recommendations
│   ├── lesson_organization_service.py    # ORGANIZES relationships (MOC pattern)
│   └── lesson_relationship_filters.py    # Relationship filtering utilities
│
├── lesson_service.py                      # PUBLIC FACADE
│                                          # → Delegates to sub-services above
│
└── Utilities (injected dependencies):
    ├── analytics_engine.py                # Advanced learning analytics
    ├── insight_generation_service.py      # AI knowledge generation
    ├── lesson_intelligence_service.py     # BaseAnalyticsService extension
    ├── entity_retrieval.py                # Vector search + graph retrieval
    ├── advanced_inference_engine.py       # Sophisticated inference
    ├── entity_chunking_service.py         # Content chunking for RAG
    └── entity_inference_service.py        # Knowledge inference algorithms
```

## Core Sub-Services (Used by LessonService facade)

### 1. `lesson_core_service.py` - CRUD Operations
**Responsibilities:**
- Create Lessons with content and chunking
- Read Lessons with content
- Update Lessons and re-chunk content
- Delete Lessons and cleanup
- Status transitions (publish, archive)
- Content analysis integration

**Methods:**
- `create()`, `get()`, `update()`, `delete()`
- `publish()`, `archive()`
- `get_chunks()`, `analyze_content()`

---

### 2. `lesson_search_service.py` - Search and Discovery
**Responsibilities:**
- Template-based search queries
- User context-aware search
- Content similarity search
- Tag-based search
- Faceted search with filtering
- Chunk-level search
- Feature-based search
- Semantic intent search

**Methods:**
- `search_by_title_template()`, `search_with_user_context()`
- `find_similar_content()`, `search_by_tags()`
- `search_by_facets()`, `search_chunks_with_facets()`
- `search_by_features()`, `search_with_semantic_intent()`

---

### 3. `lesson_graph_service.py` - Graph Navigation
**Responsibilities:**
- Prerequisite chain discovery
- Next steps recommendations
- Graph context retrieval
- Parent-child relationships
- Knowledge gap analysis
- Learning recommendations
- Hub score caching

**Methods:**
- `find_prerequisites()`, `find_next_steps()`
- `get_lesson_with_context()`, `link_prerequisite()`
- `link_parent_child()`, `get_prerequisite_chain()`
- `analyze_knowledge_gaps()`, `get_learning_recommendations()`
- `find_time_aware_learning_path()`
- `update_hub_scores()`, `get_foundational_knowledge()`

---

### 4. `lesson_semantic_service.py` - Semantic Relationships
**Responsibilities:**
- Semantic relationship creation and management
- Cross-domain knowledge bridges
- Confidence-scored connections
- Semantic neighborhood discovery
- Relationship validation

**Methods:**
- `create_with_semantic_relationships()`
- `get_semantic_neighborhood()`
- Uses `SemanticRelationshipType` enum for typed connections

---

### 5. `lesson_mastery_service.py` - Pedagogical State Tracking
**Responsibilities:**
- Track user learning state progression
- Record when user views Lesson content
- Track in-progress learning state
- Support pedagogical search filters

**State Progression:**
```
NONE -> VIEWED -> IN_PROGRESS -> MASTERED
```

**Methods:**
- `mark_viewed()`, `mark_in_progress()`, `mark_mastered()`
- `get_learning_state()`, `get_user_progress()`

---

### 6. `lesson_practice_service.py` - Event-Driven Practice Tracking
**Responsibilities:**
- Track Lesson practice via event completion
- Update practice counts and timestamps
- Publish KnowledgePracticed events

**Event-Driven Architecture:**
- Subscribes to `CalendarEventCompleted` events
- Updates `times_practiced_in_events` count
- Updates `last_practiced_date` timestamps
- Publishes `KnowledgePracticed` events

**Methods:**
- `record_practice()`, `get_practice_count()`
- `handle_event_completed()` (event handler)

---

### 7. `lesson_ai_service.py` - Optional AI Features
**Responsibilities:**
- Semantic knowledge search (find related Lessons by meaning)
- AI-generated content summaries
- Concept explanation at different levels
- Learning path suggestions

**Architecture (ADR-030):**
- Extends `BaseAIService` (requires LLM/Embeddings)
- OPTIONAL - app functions fully without it
- Enhancement layer, not core functionality

**Note:** Lesson is a Curriculum domain - content is SHARED (no user_uid ownership).

---

### 8. `lesson_adaptive_service.py` - Adaptive Learning
**Responsibilities:**
- Personalised curriculum delivery
- SEL category-based recommendations
- Readiness assessment (prerequisites met, appropriate level)
- Learning value ranking

---

### 9. `lesson_application_discovery_service.py` - Application Discovery
**Responsibilities:**
- Reverse relationship queries answering "where is this knowledge used?"
- Activity domain discovery (events, habits, tasks, goals, choices, principles)
- Curriculum navigation (path steps, learning paths)

**Methods:**
- `find_activities_connected_to_knowledge()` — generic method for all 6 activity domains
- Domain wrappers: `find_events_applying_knowledge()`, `find_habits_reinforcing_knowledge()`,
  `find_tasks_applying_knowledge()`, `find_goals_requiring_knowledge()`,
  `find_choices_informed_by_knowledge()`, `find_principles_embodying_knowledge()`
- Curriculum: `find_path_steps_containing()`, `find_learning_paths_teaching()`

---

### 10. `lesson_context_service.py` - Context-First Recommendations
**Responsibilities:**
- Personalized knowledge recommendations using UserContext
- Readiness filtering (prerequisites met)
- Goal-based learning gap analysis
- Reinforcement suggestions (decaying mastery)

**Methods:**
- `get_ready_to_learn_for_user()` — knowledge units ready to learn
- `get_learning_gaps_for_user()` — knowledge blocking goal progress
- `get_lessons_to_reinforce_for_user()` — knowledge needing reinforcement

---

### 11. `lesson_organization_service.py` - Non-linear Navigation (MOC)
**Responsibilities:**
- ORGANIZES relationships between Lessons
- Multiple parents supported
- Order and importance metadata on edges
- Root organizer discovery

**Methods:**
- `organize()`, `unorganize()`, `reorder()`
- `get_organized_children()`, `find_organizers()`, `list_root_organizers()`

---

### 12. `lesson_relationship_filters.py` - Relationship Filtering Utilities
**Responsibilities:**
- Confidence filtering for prerequisite chains
- Strength-based relationship filtering
- Type-specific batch operations
- High-quality relationship discovery

---

## Public API

### For External Code: Use `LessonService` Facade

```python
from core.services.lesson_service import LessonService

# LessonService delegates to all sub-services automatically
lesson_service = LessonService(
    repo=lesson_backend,
    content_repo=content_backend,
    intelligence_service=intelligence,
    chunking_service=chunking,
    graph_intelligence_service=graph_intel,
    lp_service=learning_paths,
    query_builder=query_builder
)

# Use facade methods - they delegate to appropriate sub-service
await lesson_service.create(...)              # → LessonCoreService.create()
await lesson_service.search_by_tags(...)      # → LessonSearchService.search_by_tags()
await lesson_service.find_prerequisites(...)  # → LessonGraphService.find_prerequisites()
```

### For Internal Implementation: Use Sub-Services Directly

```python
from core.services.lesson.lesson_core_service import LessonCoreService

# Direct usage for focused responsibilities
core_service = LessonCoreService(
    repo=lesson_backend,
    content_repo=content_backend,
    intelligence=intelligence,
    chunking=chunking
)

await core_service.create(title="...", body="...")
```

---

## Design Patterns Used

### 1. Facade Pattern
`LessonService` provides a unified interface while delegating to specialized sub-services.

### 2. Dependency Injection
Utilities are injected into services, not directly imported.

### 3. Protocol-Based Interfaces
All backends use protocol interfaces (e.g., `LessonOperations`).

### 4. Two-Tier Intelligence (ADR-030)
Separation of graph analytics from AI features.

| Layer | Service | Dependencies |
|-------|---------|--------------|
| Analytics | `lesson_intelligence_service.py` | Graph + Python (NO AI) |
| AI | `lesson_ai_service.py` | LLM + Embeddings (optional) |

---

## Similar Patterns in Other Domains

| Domain | Directory | Facade | Sub-Services |
|--------|-----------|--------|--------------|
| **Lesson** | `/lesson/` | `lesson_service.py` | 12 sub-services |
| **KU** | `/ku/` | `ku_service.py` | 2 sub-services |
| **Goals** | `/goals/` | `goaps_service.py` | 8 sub-services |
| **Habits** | `/habits/` | `habits_service.py` | 8 sub-services |

---

## References

- **CLAUDE.md**: Project architectural patterns and conventions
- **Protocol definitions**: `/core/ports/curriculum_protocols.py`
- **Domain models**: `/core/models/lesson/lesson.py`, `/core/models/lesson/lesson_dto.py`
- **Bootstrap**: `/services_bootstrap.py` (composition root)
- **ADR-030**: Intelligence services architecture (graph analytics vs AI)
