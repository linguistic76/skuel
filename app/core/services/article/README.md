# Article Sub-Services Architecture

This directory contains modular sub-services for Article (teaching composition) operations following the **Facade Pattern**.

## Architecture Overview

```
/core/services/
├── article/                                # Domain sub-services (THIS DIRECTORY)
│   ├── article_core_service.py             # CRUD operations
│   ├── article_search_service.py           # Search and discovery
│   ├── article_graph_service.py            # Graph traversal, prerequisites
│   ├── article_semantic_service.py         # Semantic relationships
│   ├── article_mastery_service.py          # Pedagogical state tracking
│   ├── article_practice_service.py         # Event-driven practice tracking
│   ├── article_ai_service.py              # Optional AI features
│   ├── article_adaptive_service.py        # Adaptive learning recommendations
│   ├── article_organization_service.py    # ORGANIZES relationships (MOC pattern)
│   └── article_relationship_helpers.py    # Relationship filtering utilities
│
├── article_service.py                      # PUBLIC FACADE
│                                           # → Delegates to sub-services above
│
└── Utilities (injected dependencies):
    ├── analytics_engine.py                # Advanced learning analytics
    ├── insight_generation_service.py      # AI knowledge generation
    ├── article_intelligence_service.py    # BaseAnalyticsService extension
    ├── entity_retrieval.py                # Vector search + graph retrieval
    ├── advanced_inference_engine.py       # Sophisticated inference
    ├── entity_chunking_service.py         # Content chunking for RAG
    └── entity_inference_service.py        # Knowledge inference algorithms
```

## Core Sub-Services (Used by ArticleService facade)

### 1. `article_core_service.py` - CRUD Operations
**Responsibilities:**
- Create Articles with content and chunking
- Read Articles with content
- Update Articles and re-chunk content
- Delete Articles and cleanup
- Status transitions (publish, archive)
- Content analysis integration

**Methods:**
- `create()`, `get()`, `update()`, `delete()`
- `publish()`, `archive()`
- `get_chunks()`, `analyze_content()`

---

### 2. `article_search_service.py` - Search and Discovery
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

### 3. `article_graph_service.py` - Graph Navigation
**Responsibilities:**
- Prerequisite chain discovery
- Next steps recommendations
- Graph context retrieval
- Parent-child relationships
- Knowledge gap analysis
- Learning recommendations
- Context-first user queries
- Application discovery (reverse relationships)
- Hub score caching

**Methods:**
- `find_prerequisites()`, `find_next_steps()`
- `get_article_with_context()`, `link_prerequisite()`
- `link_parent_child()`, `get_prerequisite_chain()`
- `analyze_knowledge_gaps()`, `get_learning_recommendations()`
- `get_ready_to_learn_for_user()`, `get_learning_gaps_for_user()`
- `find_tasks_applying_knowledge()`, `find_goals_requiring_knowledge()`

---

### 4. `article_semantic_service.py` - Semantic Relationships
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

### 5. `article_mastery_service.py` - Pedagogical State Tracking
**Responsibilities:**
- Track user learning state progression
- Record when user views Article content
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

### 6. `article_practice_service.py` - Event-Driven Practice Tracking
**Responsibilities:**
- Track Article practice via event completion
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

### 7. `article_ai_service.py` - Optional AI Features
**Responsibilities:**
- Semantic knowledge search (find related Articles by meaning)
- AI-generated content summaries
- Concept explanation at different levels
- Learning path suggestions

**Architecture (ADR-030):**
- Extends `BaseAIService` (requires LLM/Embeddings)
- OPTIONAL - app functions fully without it
- Enhancement layer, not core functionality

**Note:** Article is a Curriculum domain - content is SHARED (no user_uid ownership).

---

### 8. `article_adaptive_service.py` - Adaptive Learning
**Responsibilities:**
- Personalised curriculum delivery
- SEL category-based recommendations
- Readiness assessment (prerequisites met, appropriate level)
- Learning value ranking

---

### 9. `article_organization_service.py` - Non-linear Navigation (MOC)
**Responsibilities:**
- ORGANIZES relationships between Articles
- Multiple parents supported
- Order and importance metadata on edges
- Root organizer discovery

**Methods:**
- `organize()`, `unorganize()`, `reorder()`
- `get_organized_children()`, `find_organizers()`, `list_root_organizers()`

---

### 10. `article_relationship_helpers.py` - Relationship Filtering Utilities
**Responsibilities:**
- Confidence filtering for prerequisite chains
- Strength-based relationship filtering
- Type-specific batch operations
- High-quality relationship discovery

---

## Public API

### For External Code: Use `ArticleService` Facade

```python
from core.services.article_service import ArticleService

# ArticleService delegates to all sub-services automatically
article_service = ArticleService(
    repo=article_backend,
    content_repo=content_backend,
    intelligence_service=intelligence,
    chunking_service=chunking,
    graph_intelligence_service=graph_intel,
    lp_service=learning_paths,
    query_builder=query_builder
)

# Use facade methods - they delegate to appropriate sub-service
await article_service.create(...)              # → ArticleCoreService.create()
await article_service.search_by_tags(...)      # → ArticleSearchService.search_by_tags()
await article_service.find_prerequisites(...)  # → ArticleGraphService.find_prerequisites()
```

### For Internal Implementation: Use Sub-Services Directly

```python
from core.services.article.article_core_service import ArticleCoreService

# Direct usage for focused responsibilities
core_service = ArticleCoreService(
    repo=article_backend,
    content_repo=content_backend,
    intelligence=intelligence,
    chunking=chunking
)

await core_service.create(title="...", body="...")
```

---

## Design Patterns Used

### 1. Facade Pattern
`ArticleService` provides a unified interface while delegating to specialized sub-services.

### 2. Dependency Injection
Utilities are injected into services, not directly imported.

### 3. Protocol-Based Interfaces
All backends use protocol interfaces (e.g., `ArticleOperations`).

### 4. Two-Tier Intelligence (ADR-030)
Separation of graph analytics from AI features.

| Layer | Service | Dependencies |
|-------|---------|--------------|
| Analytics | `article_intelligence_service.py` | Graph + Python (NO AI) |
| AI | `article_ai_service.py` | LLM + Embeddings (optional) |

---

## Similar Patterns in Other Domains

| Domain | Directory | Facade | Sub-Services |
|--------|-----------|--------|--------------|
| **Article** | `/article/` | `article_service.py` | 10 sub-services |
| **KU** | `/ku/` | `ku_service.py` | 2 sub-services |
| **Goals** | `/goals/` | `goals_service.py` | 9 sub-services |
| **Habits** | `/habits/` | `habits_service.py` | 8 sub-services |

---

## References

- **CLAUDE.md**: Project architectural patterns and conventions
- **Protocol definitions**: `/core/ports/curriculum_protocols.py`
- **Domain models**: `/core/models/article/article.py`, `/core/models/article/article_dto.py`
- **Bootstrap**: `/services_bootstrap.py` (composition root)
- **ADR-030**: Intelligence services architecture (graph analytics vs AI)
