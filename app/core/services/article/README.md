# KU Sub-Services Architecture

This directory contains modular sub-services for Knowledge Unit operations following the **Facade Pattern**.

## Architecture Overview

```
/core/services/
├── ku/                              # Domain sub-services (THIS DIRECTORY)
│   ├── ku_core_service.py           # CRUD operations (712 lines)
│   ├── ku_search_service.py         # Search and discovery (618 lines)
│   ├── ku_graph_service.py          # Graph traversal, prerequisites (1,985 lines)
│   ├── ku_semantic_service.py       # Semantic relationships (555 lines)
│   ├── ku_interaction_service.py    # Pedagogical state tracking (386 lines)
│   ├── ku_practice_service.py       # Event-driven practice tracking (195 lines)
│   ├── ku_ai_service.py             # Optional AI features (415 lines)
│   └── ku_relationship_helpers.py   # Relationship filtering utilities (383 lines)
│
├── ku_service.py                    # PUBLIC FACADE (1,161 lines)
│                                    # → Delegates to sub-services above
│
└── Utilities (injected dependencies):
    ├── analytics_engine.py          # Advanced learning analytics (1,347 lines)
    ├── insight_generation_service.py # AI knowledge generation (1,074 lines)
    ├── ku_intelligence_service.py   # BaseAnalyticsService extension (727 lines)
    ├── entity_retrieval.py          # Vector search + graph retrieval (641 lines)
    ├── advanced_inference_engine.py  # Sophisticated inference (710 lines)
    ├── entity_chunking_service.py   # Content chunking for RAG (489 lines)
    └── entity_inference_service.py  # Knowledge inference algorithms (479 lines)
```

## Core Sub-Services (Used by KuService facade)

### 1. `ku_core_service.py` - CRUD Operations
**Responsibilities:**
- Create knowledge units with content and chunking
- Read knowledge units with content
- Update knowledge units and re-chunk content
- Delete knowledge units and cleanup
- Status transitions (publish, archive)
- Content analysis integration

**Methods:**
- `create()`, `get()`, `update()`, `delete()`
- `publish()`, `archive()`
- `get_chunks()`, `analyze_content()`

---

### 2. `ku_search_service.py` - Search and Discovery
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

### 3. `ku_graph_service.py` - Graph Navigation
**Responsibilities:**
- Prerequisite chain discovery
- Next steps recommendations
- Graph context retrieval (Phase 1-4)
- Parent-child relationships
- Knowledge gap analysis
- Learning recommendations
- Context-first user queries
- Application discovery (reverse relationships)
- Hub score caching

**Methods:**
- `find_prerequisites()`, `find_next_steps()`
- `get_knowledge_with_context()`, `link_prerequisite()`
- `link_parent_child()`, `get_prerequisite_chain()`
- `analyze_knowledge_gaps()`, `get_learning_recommendations()`
- `get_ready_to_learn_for_user()`, `get_learning_gaps_for_user()`
- `find_tasks_applying_knowledge()`, `find_goals_requiring_knowledge()`

**Note:** This is the largest sub-service (~2,000 lines) due to comprehensive graph operations. The file is well-organized with section headers and was evaluated for splitting but kept unified due to high internal cohesion.

---

### 4. `ku_semantic_service.py` - Semantic Relationships
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

### 5. `ku_interaction_service.py` - Pedagogical State Tracking
**Responsibilities:**
- Track user learning state progression
- Record when user views KU content
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

### 6. `ku_practice_service.py` - Event-Driven Practice Tracking
**Responsibilities:**
- Track KU practice via event completion
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

### 7. `ku_ai_service.py` - Optional AI Features
**Responsibilities:**
- Semantic knowledge search (find related KUs by meaning)
- AI-generated content summaries
- Concept explanation at different levels
- Learning path suggestions

**Architecture (ADR-030):**
- Extends `BaseAIService` (requires LLM/Embeddings)
- OPTIONAL - app functions fully without it
- Enhancement layer, not core functionality

**Note:** KU is a Curriculum domain - content is SHARED (no user_uid ownership).

---

### 8. `ku_relationship_helpers.py` - Relationship Filtering Utilities
**Responsibilities:**
- Confidence filtering for prerequisite chains
- Strength-based relationship filtering
- Type-specific batch operations
- High-quality relationship discovery

**Key Features:**
- `build_high_confidence_prerequisites_query()`
- `filter_by_relationship_strength()`
- Quality-based knowledge graph queries

---

## Top-Level Utilities (Injected Dependencies)

These services live at `/core/services/` level and are **used BY** the sub-services, not duplicates:

### `analytics_engine.py` - Advanced Analytics
**Purpose:** Learning pattern recognition, knowledge-aware priority scoring, insight generation

**Use cases:**
- Detect learning patterns (knowledge building, cross-domain application, mastery validation)
- Calculate knowledge mastery progression
- Generate learning insights
- Track knowledge application patterns

**Injected into:** Tasks service, analytics routes

---

### `insight_generation_service.py` - AI Knowledge Generation
**Purpose:** AI-powered automatic knowledge extraction from completed tasks

**Use cases:**
- Pattern recognition for best practices and anti-patterns
- Insight generation from successful task completion patterns
- Knowledge quality scoring and curation
- Automatic knowledge unit creation from task insights

**Injected into:** Tasks service for task-to-knowledge conversion

---

### `ku_intelligence_service.py` - BaseAnalyticsService Extension
**Purpose:** Graph-native intelligence features (NO AI dependencies per ADR-030)

**Use cases:**
- Semantic relationship analysis
- Concept mapping and prerequisites
- Learning path generation
- Knowledge substance tracking

**Architecture:**
- Extends `BaseAnalyticsService` (pure graph queries + Python)
- NO LLM or embeddings dependencies
- Returns `Result[T]` for error handling

---

### `entity_retrieval.py` - Unified Retrieval
**Purpose:** THE single retrieval service for SKUEL combining vector search, graph traversal, and intelligent ranking

**Use cases:**
- Hybrid search (vector embeddings + graph structure)
- User context-aware retrieval
- Personalized knowledge discovery
- Multi-strategy ranking

**Injected into:** Search routes, personalized discovery adapter

---

### `advanced_inference_engine.py` - Sophisticated Inference
**Purpose:** Advanced knowledge detection algorithms building on `EntityInferenceService`

**Use cases:**
- Multi-algorithm content analysis
- Cross-domain knowledge relationship mapping
- Advanced confidence scoring
- Knowledge validation feedback loops

**Relationship:** `entity_inference_service.py` imports and delegates to this engine

---

### `entity_chunking_service.py` - Content Chunking
**Purpose:** RAG (Retrieval-Augmented Generation) content chunking for embeddings

**Use cases:**
- Split long content into semantic chunks
- Maintain chunk metadata and relationships
- Support chunk-level search and retrieval
- Enable fine-grained content analysis

**Injected into:** KU core service for content processing

---

### `entity_inference_service.py` - Knowledge Inference
**Purpose:** Automatic knowledge inference algorithms for enhanced task models

**Use cases:**
- Infer knowledge connections from task content
- Detect learning opportunities
- Generate knowledge insights
- Calculate confidence scores for inferred relationships

**Injected into:** Tasks service for automatic knowledge tagging

---

## Public API

### For External Code: Use `KuService` Facade

```python
from core.services.ku_service import KuService

# KuService delegates to all sub-services automatically
ku_service = KuService(
    repo=knowledge_backend,
    content_repo=content_backend,
    intelligence_service=intelligence,
    chunking_service=chunking,      # Utility injected
    graph_intelligence_service=graph_intel,
    lp_service=learning_paths,
    query_builder=query_builder
)

# Use facade methods - they delegate to appropriate sub-service
await ku_service.create(...)           # → KuCoreService.create()
await ku_service.search_by_tags(...)   # → KuSearchService.search_by_tags()
await ku_service.find_prerequisites()  # → KuGraphService.find_prerequisites()
```

### For Internal Implementation: Use Sub-Services Directly

```python
from core.services.ku.ku_core_service import KuCoreService

# Direct usage for focused responsibilities
core_service = KuCoreService(
    repo=knowledge_backend,
    content_repo=content_backend,
    intelligence=intelligence,
    chunking=chunking
)

await core_service.create(title="...", body="...")
```

---

## Design Patterns Used

### 1. Facade Pattern
`KuService` provides a unified interface while delegating to specialized sub-services.

**Benefits:**
- Single entry point for external code
- Backward compatibility maintained
- Sub-services can evolve independently
- Clear separation of concerns

### 2. Dependency Injection
Utilities are injected into services, not directly imported.

**Benefits:**
- Easy to test (mock dependencies)
- Flexible composition
- No circular dependencies
- Clear dependency graph

### 3. Protocol-Based Interfaces
All backends use protocol interfaces (e.g., `KuOperations`).

**Benefits:**
- Type-safe without concrete dependencies
- Easy to swap implementations
- Clean architecture boundaries
- MyPy validation

### 4. Two-Tier Intelligence (ADR-030)
Separation of graph analytics from AI features.

| Layer | Service | Dependencies |
|-------|---------|--------------|
| Analytics | `ku_intelligence_service.py` | Graph + Python (NO AI) |
| AI | `ku_ai_service.py` | LLM + Embeddings (optional) |

---

## Similar Patterns in Other Domains

This same architecture is used consistently across SKUEL:

| Domain | Directory | Facade | Sub-Services | Utilities |
|--------|-----------|--------|--------------|-----------|
| **Knowledge** | `/ku/` | `ku_service.py` | 8 sub-services | 7 utilities |
| **Goals** | `/goals/` | `goals_service.py` | 5 sub-services | 2 utilities |
| **Habits** | `/habits/` | `habits_service.py` | 7 sub-services | 1 utility |

---

## Architecture Decision: ku_graph_service.py Size

The graph service is ~2,000 lines, making it the largest file. A split was evaluated:

| Option | Verdict |
|--------|---------|
| Split by consumer (traversal/analysis/discovery) | Added coordination overhead |
| Split by concern (prerequisite/recommendation/cross-domain) | Overlapping dependencies |
| **Keep unified** | **Chosen** - cohesive purpose, well-organized sections |

**Rationale:**
- All methods relate to "graph operations for KU"
- Shared dependencies (repo, neo4j, graph_intel)
- Internal coupling (context-first methods call discovery methods)
- Well-organized with `# ====` section headers

**Future option:** If split becomes necessary, extract the 8 `find_*` methods into `ku_application_discovery_service.py` (~515 lines).

---

## Version History

- **v5.0 (2026-01-20)**: Updated to reflect 8 sub-services + 7 utilities (added interaction, practice, AI, helpers, intelligence)
- **v4.0 (2025-10-10)**: Decomposed monolithic service into 5 focused sub-services
- **v3.0**: Previous monolithic architecture with all operations in one service

---

## References

- **CLAUDE.md**: Project architectural patterns and conventions
- **Protocol definitions**: `/core/ports/ku_protocols.py`
- **Domain models**: `/core/models/ku/`
- **Bootstrap**: `/services_bootstrap.py` (composition root)
- **ADR-030**: Intelligence services architecture (graph analytics vs AI)
