---
title: Askesis Search Architecture - Clean & Independent
updated: 2026-01-12
status: current
category: guides
tags: [architecture, askesis, guides, search]
related: []
---

# Askesis Search Architecture - Clean & Independent

**Date**: October 8, 2025 (Initial), January 12, 2026 (Updated)
**Status**: ✅ Enhanced with semantic search via EmbeddingsService

## Executive Summary

**Good News**: Askesis does NOT use the deprecated `/core/models/search/` models. It has its own clean search integration through transcription models.

**January 2026 Update**: Askesis now has fully implemented semantic search via `EmbeddingsService`, enabling vector similarity search for knowledge discovery.

## Askesis Search Integration

### What Askesis Uses

Askesis uses **query infrastructure search models**:

```python
# From /core/models/askesis/askesis.py:
from core.models.search_models import FacetSetRequest as FacetSetSchema
from core.models.search_models import SearchQueryRequest as SearchQuerySchema
from core.models.search_models import SearchResultDTO as CrossDomainSearchResultsSchema
```

### Search Boundary Models

Located at `/core/models/search_models.py`:
- `FacetSetRequest` - Pydantic request model for search facets
- `SearchQueryRequest` - Pydantic request model for complete search queries
- `SearchResultDTO` - Cross-domain search result DTO

**These are separate from and unrelated to**:
- ❌ `/core/models/search/search_pure.py` (deprecated)
- ❌ `/core/models/search/search_dto.py` (deprecated)
- ❌ `SearchIntent` enum (deprecated)

## How Askesis Performs Search

### 1. Request Model (AskesisResponse)

```python
@dataclass(frozen=True)
class AskesisResponse:
    """AI Learning Assistant response with search integration"""

    # Search integration
    search_performed: bool = False
    search_query: SearchQuerySchema | None = None  # Transcription model
    search_results: CrossDomainSearchResultsSchema | None = None  # Transcription DTO

    # Extraction
    extraction: FacetSetSchema | None = None  # Transcription facets
```

### 2. Search Workflow in Askesis

```
User Query → Askesis Service
    ↓
Transcription Search (if needed)
    ↓
SearchQueryRequest (transcription model)
    ↓
SearchResultDTO (cross-domain results)
    ↓
AskesisResponse (with search results)
```

### 3. Intent System

Askesis uses `Intent` enum from `core/models/enums`, NOT `SearchIntent`:

```python
from core.models.enums import Intent

# User intent detection
detected_intent: Intent | None = None  # LEARN, PRACTICE, etc.
```

**Intent enum locations**:
- ✅ `core.models.enums.Intent` - Used by Askesis
- ✅ `query.QueryIntent` - Infrastructure queries
- ❌ `search.SearchIntent` - DEPRECATED

## Files Audited

### ✅ Askesis Models (Clean)
```bash
/core/models/askesis/
├── askesis.py               # Uses transcription models
├── askesis_dto.py           # No search imports
├── askesis_request.py       # No search imports
├── askesis_converters.py    # No search imports
└── __init__.py              # Clean exports
```

**Result**: No deprecated search imports found

### ✅ Askesis Service (Clean)
```bash
/core/services/askesis_service.py         # Main facade (~1,050 lines)
/core/services/askesis/                    # 9 sub-services
├── user_state_analyzer.py
├── action_recommendation_engine.py
├── state_scoring.py                       # Pure functions (January 2026)
├── query_processor.py                     # RAG orchestration (~500 lines)
├── intent_classifier.py                   # Intent classification (January 2026)
├── response_generator.py                  # Action generation (January 2026)
├── entity_extractor.py
├── context_retriever.py
└── types.py
```

**Result**: No deprecated search imports found

### ✅ Askesis Routes (Clean)
```bash
/adapters/inbound/
├── askesis_api.py               # Clean
├── askesis_intelligence_api.py  # Clean
├── askesis_routes.py            # Entry point (wiring)
└── askesis_ui.py                # Clean
```

**Result**: No deprecated search imports found

## Search Dependencies

### What Askesis Depends On

1. **Transcription Models** (/core/models/transcription/)
   - SearchQueryRequest
   - SearchResultDTO
   - FacetSetRequest

2. **Shared Enums** (/core/models/enums/)
   - Intent (not SearchIntent)
   - GuidanceMode
   - Personality
   - ResponseTone

3. **Query Infrastructure** (/adapters/persistence/neo4j/query/, /core/models/query_types.py)
   - QueryIntent
   - ApocQueryBuilder

4. **Knowledge Models** (/core/models/ku/)
   - Per-domain DTOs (CurriculumDTO, TaskDTO, etc.)

### What Askesis Does NOT Depend On

❌ `/core/models/search/` - Deprecated directory (not used)
❌ `SearchIntent` enum - Deprecated (not used)
❌ `SearchQuery` class - Deprecated (not used)
❌ `SearchResult` class - Deprecated (not used)

## Why Askesis is Unaffected

### 1. Different Search Abstraction

Askesis uses **transcription-domain search** which is:
- Domain-specific (for transcribed content)
- Integration-focused (how transcriptions connect to knowledge)
- Separate codebase (transcription models, not search models)

### 2. Clean Architecture

```
Askesis Layer:
├── Uses Intent from core/models/enums (universal)
├── Uses QueryIntent from query infrastructure (universal)
└── Uses SearchQueryRequest from transcription (domain-specific)

DOES NOT USE:
└── SearchIntent from deprecated search (deprecated)
```

### 3. Already Aligned with Best Practices

Askesis already follows the patterns we're moving toward:
- ✅ Uses shared enums for intents
- ✅ Uses query infrastructure for graph traversal
- ✅ Uses domain-specific models (transcription)
- ✅ Doesn't mix concerns (no deprecated search imports)

## Semantic Search Implementation (January 2026)

### New Capabilities

Askesis now includes fully implemented semantic search via `ContextRetriever`:

```python
# ContextRetriever._find_similar_knowledge()
async def _find_similar_knowledge(self, query: str, _user_uid: str) -> list[tuple[str, float, str]]:
    """
    Find semantically similar knowledge units.

    Returns: list of (uid, similarity_score, title) tuples
    """
    # 1. Create query embedding
    query_embedding = await self.embeddings_service.create_embedding(query)

    # 2. Fetch KUs with stored embeddings
    ku_query = """
    MATCH (ku:Curriculum) WHERE ku.embedding IS NOT NULL
    RETURN ku.uid, ku.title, ku.embedding LIMIT 100
    """

    # 3. Cosine similarity matching (threshold 0.6, top_k=5)
    similar = self.embeddings_service.find_similar(
        query_embedding=query_embedding,
        embeddings=embeddings_list,
        threshold=0.6, top_k=5
    )
```

### Knowledge Gap Analysis

`ContextRetriever` now performs comprehensive gap analysis:

1. **`_build_user_learning_context_query()`** - Comprehensive Cypher query with 5 OPTIONAL MATCH clauses:
   - Current knowledge (mastered KUs)
   - Active learning (in-progress KUs)
   - Active tasks with knowledge links
   - Current goals with knowledge requirements
   - Active habits reinforcing knowledge

2. **`_analyze_blocked_knowledge_prerequisites()`** - Identifies:
   - Knowledge blocked by missing prerequisites
   - Prerequisite chains preventing progress
   - Quick wins (0-1 prerequisites)
   - High-impact items (many dependents)

3. **`_identify_quick_wins_and_high_impact()`** - Classification:
   - **Quick wins**: Items with 0-1 prerequisites (easy to start)
   - **High impact**: Items that unlock many dependents

### Integration with EmbeddingsService

```python
# EmbeddingsService API used by Askesis:
create_embedding(text: str) -> list[float]           # Create vector embedding
find_similar(query_embedding, embeddings, threshold, top_k)  # Cosine similarity search
```

### Prerequisites for Semantic Search

- KUs must have `embedding` field populated (via ingestion or batch job)
- `EmbeddingsService` must be available (requires OPENAI_API_KEY)
- `GraphIntelligenceService` for query execution

---

## Conclusion

### ✅ No Action Needed for Askesis

**Askesis is already clean and properly architected**:

1. **No deprecated imports** - Doesn't use `/core/models/search/`
2. **Proper abstractions** - Uses transcription models for transcription search
3. **Aligned with new patterns** - Uses shared enums and query infrastructure
4. **No migration required** - Already follows best practices

### Architecture Validation

```
✅ Askesis Models     - Clean (no deprecated search)
✅ Askesis Service    - Clean (no deprecated search)
✅ Askesis Routes     - Clean (no deprecated search)
✅ Askesis Tests      - TBD (separate audit)
```

## Recommendation

**No changes needed** to Askesis as part of Phase 3 search cleanup.

Askesis can continue using transcription models for its search integration. The transcription search models serve a different purpose (transcription-specific facet extraction and cross-domain linking) and are not part of the deprecated search infrastructure.

## Future Enhancements (Optional)

If we want to align Askesis with the new Simple Search, we could:

1. **Add Simple Search Integration** (optional):
   ```python
   from core.models.search_request import SearchRequest, SearchResponse

   # Use Simple Search for knowledge lookup
   search_request = SearchRequest(
       query_text=user_query,
       domain=Domain.KNOWLEDGE,
       sel_category=detected_category
   )
   ```

2. **Keep Transcription Search** (current):
   - Continue using transcription models for transcription-specific searches
   - Use Simple Search for general knowledge lookup
   - Both can coexist

But this is **not required** - Askesis is already clean and working well.

## References

- Askesis Models: `/core/models/askesis/`
- Transcription Models: `/core/models/transcription/`
- Simple Search: `/core/models/search_request.py`
- Query Infrastructure: `/adapters/persistence/neo4j/query/`
- Deprecated Search: `/core/models/search/` (don't use)
