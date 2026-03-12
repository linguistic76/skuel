# Askesis Semantic Intelligence Roadmap

**Status:** Deferred enhancements after vector search fix (March 2026)

## Context

Phase 1-3 wired `Neo4jVectorSearchService` into Askesis `ContextRetriever`, replacing the broken `embeddings_service.find_similar()` call with native Neo4j vector index search (`db.index.vector.queryNodes()`). Semantic search now works for all queries (keyword gate removed).

## Deferred Work

### 1. Durable Conversation Persistence
Replace in-memory `ConversationContext` with Neo4j-backed sessions. Enables conversation history survival across server restarts and multi-turn Socratic dialogue that persists.

See: `docs/roadmap/conversation-neo4j-persistence-deferred.md`

### 2. End-to-End Askesis Testing
Integration tests that exercise the full RAG pipeline: query -> intent classification -> vector search -> context assembly -> LLM response. Currently only unit tests with mocked services exist.

### 3. Learning-Aware Semantic Search
Use `vector_search_service.learning_aware_search()` instead of generic `find_similar_by_text()`. This boosts unseen content (+15%), deprioritizes mastered content (-20%), and prioritizes in-progress content (+10%) — making "what should I learn next?" queries return personalized results.

### 4. LS Bundle Semantic Enrichment
When loading LS bundles, use semantic search to find related Resources beyond explicit `CITES_RESOURCE` edges. This surfaces content the curriculum author didn't explicitly link but is semantically relevant to the learning step.

### 5. Citation Service Semantic Relationships
Enrich `AskesisCitationService` with semantic relationship data. When formatting citations, include semantically related entities to give Askesis richer context for Socratic responses.

### 6. Knowledge Gap Analysis with Semantic Fallback
When `analyze_knowledge_gaps()` finds blocked knowledge, use semantic search to suggest alternative learning paths — content that covers similar concepts but through different prerequisite chains.
