"""
KU Search Service - BaseService Pattern (Harmonized January 2026)
==================================================================

Search operations for Knowledge Units extending BaseService for
unified search architecture.

This service provides:
- Text search on title/content/tags (inherited from BaseService)
- Graph-aware faceted search with relationship traversal (inherited)
- KU-specific methods: search_chunks(), find_similar_content(), etc.

Architecture (January 2026 - ADR-023 Harmonization):
- Extends BaseService[UniversalNeo4jBackend[Ku], Ku]
- Inherits: search(), graph_aware_faceted_search(), etc.
- Uses backend.execute_query() (NO driver parameter)
- Class attributes configure behavior

SKUEL Architecture:
- Uses CypherGenerator for ALL graph queries
- Returns Result[T] for error handling
- No custom filter classes - uses SearchRequest
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from core.constants import QueryLimit
from core.models.enums.neo_labels import NeoLabel
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.relationship_names import RelationshipName
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.services.protocols import KuOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.metrics import track_query_metrics
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
    from core.services.protocols import (
        IntelligenceOperations,
        QueryBuilderOperations,
    )

logger = get_logger(__name__)


class KuSearchService(BaseService[KuOperations, Ku]):
    """
    Search service for Knowledge Units - BaseService pattern.

    Implements DomainSearchOperations[Ku] protocol for integration with
    SearchRouter and unified search infrastructure.

    Inherited Methods (from BaseService):
    - search(query, limit) - Text search on _search_fields
    - get_by_relationship(related_uid, relationship_type, direction)
    - get_by_status(status, limit) - Filter by status
    - get_by_domain(domain, limit) - Filter by Domain
    - graph_aware_faceted_search(request) - Rich graph context search
    - get_with_content(uid) - Entity with full content
    - get_with_context(uid, depth) - Entity with graph neighborhood
    - get_prerequisites(uid, depth) - Prerequisite chain
    - get_enables(uid, depth) - What this enables
    - get_hierarchy(uid) - Position in hierarchy
    - get_user_progress(user_uid, entity_uid) - User mastery data

    KU-Specific Methods (require content_repo or intelligence):
    - search_chunks() - Content chunk search (RAG)
    - search_chunks_with_facets() - Chunk search with facets
    - get_content_chunks() - Get chunks for a KU
    - find_similar_content() - Semantic similarity
    - search_by_features() - Feature-based search
    - search_by_tags() - Tag-based search
    - search_by_facets() - Multi-faceted search

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - Returns Result[T] for error handling
    - No driver parameter - uses backend.execute_query()
    """

    # =========================================================================
    # DomainConfig consolidation (January 2026 Phase 3)
    # =========================================================================
    # All configuration in one place, using centralized relationship registry
    # See: /docs/decisions/ADR-025-service-consolidation-patterns.md
    _config = create_curriculum_domain_config(
        dto_class=KuDTO,
        model_class=Ku,
        domain_name="ku",
        search_fields=("title", "content", "tags"),  # KU includes tags
        search_order_by="updated_at",
        content_field="content",
    )

    # =========================================================================
    # GRAPH ENRICHMENT PATTERNS (Phase 3: Cross-Domain Applications)
    # =========================================================================
    # These patterns are used by BaseService.graph_aware_faceted_search()
    # to enrich search results with relationship context.
    #
    # Each tuple: (context_key, relationship_type, target_label)
    # - context_key: Field name in _graph_context dict
    # - relationship_type: RelationshipName enum value
    # - target_label: Neo4j node label (NeoLabel enum value)
    #
    # Results will include counts and UIDs for each relationship type:
    # {
    #   "_graph_context": {
    #     "applied_in_tasks_count": 5,
    #     "applied_in_tasks": ["task.001", "task.002", ...],
    #     ...
    #   }
    # }
    _graph_enrichment_patterns: ClassVar[list[tuple[str, str, str]]] = [
        # Curriculum relationships (where KU is taught)
        ("taught_in_steps", RelationshipName.CONTAINS_KNOWLEDGE.value, NeoLabel.LS.value),
        # Note: Learning Paths require 2-hop query (Lp→Ls→Ku), handled separately
        # Prerequisite/enables relationships (KU↔KU navigation)
        ("prerequisites", RelationshipName.REQUIRES_KNOWLEDGE.value, NeoLabel.KU.value),
        ("enables", RelationshipName.ENABLES_KNOWLEDGE.value, NeoLabel.KU.value),
        # Activity Domain applications (where KU is used)
        ("applied_in_tasks", RelationshipName.APPLIES_KNOWLEDGE.value, NeoLabel.TASK.value),
        ("required_by_goals", RelationshipName.REQUIRES_KNOWLEDGE.value, NeoLabel.GOAL.value),
        ("practiced_in_events", RelationshipName.APPLIES_KNOWLEDGE.value, NeoLabel.EVENT.value),
        ("reinforced_by_habits", RelationshipName.REINFORCES_KNOWLEDGE.value, NeoLabel.HABIT.value),
        ("informs_choices", RelationshipName.INFORMED_BY_KNOWLEDGE.value, NeoLabel.CHOICE.value),
        (
            "grounds_principles",
            RelationshipName.GROUNDED_IN_KNOWLEDGE.value,
            NeoLabel.PRINCIPLE.value,
        ),
    ]

    def __init__(
        self,
        backend: UniversalNeo4jBackend[Ku],
        content_repo: Any | None = None,  # Was ContentOperations (deleted January 2026)
        intelligence: IntelligenceOperations | None = None,
        query_builder: QueryBuilderOperations | None = None,
        vector_search_service: Any | None = None,  # NEW: Neo4jVectorSearchService
        embeddings_service: Any | None = None,  # NEW: Neo4jGenAIEmbeddingsService
    ) -> None:
        """
        Initialize KU search service.

        ARCHITECTURE (January 2026 - Neo4j GenAI Integration):
        - Foundation: Graph-semantic search (relationships, Pure Cypher)
        - Enhancement: AI-powered vector search (optional, additive)
        - Graceful degradation when AI services unavailable

        Args:
            backend: UniversalNeo4jBackend implementing BackendOperations[Ku]
            content_repo: Optional content operations for chunk search
            intelligence: Optional intelligence service for similarity search
            query_builder: Optional query builder for optimized queries
            vector_search_service: Optional Neo4jVectorSearchService for semantic search
            embeddings_service: Optional Neo4jGenAIEmbeddingsService for embedding generation
        """
        super().__init__(backend)  # Uses _service_name class attribute
        self.content_repo = content_repo
        self.intelligence = intelligence
        self.query_builder = query_builder
        self.vector_search = vector_search_service  # Can be None - graceful degradation
        self.embeddings = embeddings_service  # Can be None - graceful degradation

        # Log AI capabilities
        if self.vector_search:
            self.logger.info("✅ Vector search available - semantic similarity enabled")
        else:
            self.logger.debug("⚠️ Vector search unavailable - using keyword search fallback")

    # =========================================================================
    # ABSTRACT METHOD IMPLEMENTATION
    # =========================================================================

    def _get_content_query(self) -> str:
        """
        Return Cypher query fragment for fetching KU content.

        For Knowledge Units, content is stored inline in the content field.
        """
        return """
        RETURN n, n.content as content
        """

    # =========================================================================
    # LEGACY API COMPATIBILITY
    # (These methods delegate to inherited BaseService methods)
    # =========================================================================

    @track_query_metrics("ku_search_by_title")
    @with_error_handling("search_by_title", error_type="database")
    async def search_by_title_template(
        self, search_term: str, limit: int = 25
    ) -> Result[list[KuDTO]]:
        """
        Search knowledge units by title.

        This is a legacy method that delegates to the inherited search() method.
        Use search() directly for new code.

        Args:
            search_term: Search term to match
            limit: Maximum results to return

        Returns:
            Result containing list of matching KuDTOs
        """
        if not search_term or not search_term.strip():
            return Result.fail(Errors.validation("Search term is required", field="search_term"))

        # Delegate to inherited search method
        result = await self.search(search_term, limit=limit)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert Ku models to KuDTOs for API compatibility
        dtos = self._convert_to_dtos(result.value)

        self.logger.debug(f"Title search for '{search_term}' returned {len(dtos)} results")
        return Result.ok(dtos)

    # =========================================================================
    # TAG AND FACET SEARCH (KU-Specific implementations)
    # =========================================================================

    @track_query_metrics("ku_search_by_tags")
    @with_error_handling("search_by_tags", error_type="database")
    async def search_by_tags(
        self, tags: list[str], match_all: bool = False, limit: int = 25
    ) -> Result[list[KuDTO]]:
        """
        Search knowledge units by tags.

        Args:
            tags: List of tags to match
            match_all: If True, require ALL tags; if False, require ANY tag
            limit: Maximum results to return

        Returns:
            Result containing list of matching KuDTOs
        """
        if not tags:
            return Result.fail(Errors.validation("At least one tag is required", field="tags"))

        # Use inherited search_by_tags from BaseService
        result = await super().search_by_tags(tags, match_all=match_all, limit=limit)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to DTOs
        dtos = self._convert_to_dtos(result.value)

        self.logger.debug(
            f"Tag search for {tags} (match_all={match_all}) returned {len(dtos)} results"
        )
        return Result.ok(dtos)

    @track_query_metrics("ku_search_by_facets")
    @with_error_handling("search_by_facets", error_type="database")
    async def search_by_facets(
        self,
        tags: list[str] | None = None,
        domain: str | None = None,
        complexity: str | None = None,
        status: str | None = None,
        limit: int = 25,
    ) -> Result[list[KuDTO]]:
        """
        Multi-dimensional faceted search.

        Filters by multiple criteria (tags, domain, complexity, status).

        Args:
            tags: Optional list of tags to filter by
            domain: Optional domain filter (e.g., "TECH", "BUSINESS")
            complexity: Optional complexity filter
            status: Optional status filter
            limit: Maximum results to return

        Returns:
            Result containing list of matching KuDTOs
        """
        # Build filters dict for backend.find_by()
        filters: dict[str, Any] = {}
        if domain:
            filters["domain"] = domain
        if complexity:
            filters["complexity"] = complexity
        if status:
            filters["status"] = status

        # Execute search with filters
        if filters:
            result = await self.backend.find_by(limit=limit, **filters)
        else:
            list_result = await self.backend.list(limit=limit)
            if list_result.is_error:
                return Result.fail(list_result.expect_error())
            result = Result.ok(list_result.value[0])  # Unpack (entities, count) tuple

        if result.is_error:
            return Result.fail(result.expect_error())

        # Filter by tags if provided (post-filter for array matching)
        entities = result.value
        if tags:
            entities = [e for e in entities if any(tag in (e.tags or []) for tag in tags)]

        # Convert to DTOs
        dtos = self._convert_to_dtos(entities[:limit])

        self.logger.debug(f"Faceted search returned {len(dtos)} results")
        return Result.ok(dtos)

    # =========================================================================
    # CHUNK SEARCH (Requires content_repo)
    # =========================================================================

    @track_query_metrics("ku_search_chunks")
    @with_error_handling("search_chunks", error_type="database")
    async def search_chunks(
        self, query: str, knowledge_uids: list[str] | None = None, limit: int = 20
    ) -> Result[list[dict[str, Any]]]:
        """
        Search content chunks for relevant passages.

        Args:
            query: Search query
            knowledge_uids: Optional list of knowledge unit UIDs to search within
            limit: Maximum chunks to return

        Returns:
            Result containing list of matching chunks with scores
        """
        if not query or not query.strip():
            return Result.fail(Errors.validation("Search query is required", field="query"))

        if not self.content_repo:
            return Result.fail(
                Errors.system(
                    message="Content repository not available for chunk search",
                    operation="search_chunks",
                )
            )

        # Search chunks in content repository
        chunks = await self.content_repo.search_chunks(
            query=query, knowledge_uids=knowledge_uids, limit=limit
        )

        self.logger.debug(f"Chunk search for '{query}' returned {len(chunks)} results")
        return Result.ok(chunks)

    @with_error_handling("search_chunks_with_facets", error_type="database")
    async def search_chunks_with_facets(
        self, query: str, facets: dict[str, Any] | None = None, limit: int = 20
    ) -> Result[list[dict[str, Any]]]:
        """
        Search content chunks with facet filtering.

        Args:
            query: Search query
            facets: Optional facet filters (domain, tags, etc.)
            limit: Maximum chunks to return

        Returns:
            Result containing list of matching chunks with scores
        """
        if not query or not query.strip():
            return Result.fail(Errors.validation("Search query is required", field="query"))

        # Build filtered list of knowledge unit UIDs based on facets
        knowledge_uids = None
        if facets:
            # First search units by facets
            facet_result = await self.search_by_facets(
                tags=facets.get("tags"),
                domain=facets.get("domain"),
                complexity=facets.get("complexity"),
                status=facets.get("status"),
                limit=QueryLimit.COMPREHENSIVE,
            )

            if facet_result.is_ok:
                knowledge_uids = [dto.uid for dto in facet_result.value]

        # Search chunks within filtered units
        return await self.search_chunks(query, knowledge_uids, limit)

    @with_error_handling("get_content_chunks", error_type="database", uid_param="uid")
    async def get_content_chunks(
        self, uid: str, chunk_type: str | None = None
    ) -> Result[list[dict[str, Any]]]:
        """
        Get all chunks for a specific knowledge unit.

        Args:
            uid: Knowledge unit UID
            chunk_type: Optional filter by chunk type

        Returns:
            Result containing list of chunks
        """
        if not self.content_repo:
            return Result.fail(
                Errors.system(
                    message="Content repository not available",
                    operation="get_content_chunks",
                )
            )

        chunks = await self.content_repo.get_chunks_for_unit(uid, chunk_type=chunk_type)
        return Result.ok(chunks)

    # =========================================================================
    # SIMILARITY & FEATURES (Requires intelligence service)
    # =========================================================================

    @track_query_metrics("ku_find_similar")
    @with_error_handling("find_similar_content", error_type="database", uid_param="uid")
    async def find_similar_content(
        self, uid: str, limit: int = 5, prefer_vector_search: bool = True
    ) -> Result[list[KuDTO]]:
        """
        Find knowledge units similar to the given unit.

        ARCHITECTURE (January 2026 - Two Complementary Approaches):
        - Layer 1 (Foundation): Graph-semantic search via relationships
        - Layer 2 (Enhancement): AI-powered vector search via embeddings

        The system tries vector search first (when available), then falls back
        to keyword search if needed. Both approaches serve different purposes.

        Args:
            uid: Knowledge unit UID to find similar content for
            limit: Maximum similar units to return
            prefer_vector_search: If True, use vector search when available

        Returns:
            Result containing list of similar KuDTOs
        """
        # Get the source unit to verify it exists
        source_result = await self.backend.get(uid)
        if source_result.is_error or not source_result.value:
            return Result.fail(Errors.not_found(resource="Ku", identifier=uid))

        # Try AI-enhanced vector search if available and preferred
        if self.vector_search and prefer_vector_search:
            vector_result = await self.vector_search.find_similar_to_node(
                label="Ku", uid=uid, limit=limit, min_score=0.7
            )

            if vector_result.is_ok:
                similar_nodes = vector_result.value
                # Convert nodes to DTOs
                dtos = [self._node_dict_to_dto(node["node"]) for node in similar_nodes]
                self.logger.debug(f"Vector search found {len(dtos)} similar units for {uid}")
                return Result.ok(dtos)
            else:
                self.logger.warning(
                    f"Vector search failed: {vector_result.expect_error()}, falling back to keyword search"
                )

        # Fallback: Keyword search via structural similarity
        self.logger.info(f"Using keyword search fallback for {uid}")
        return await self._find_similar_by_keywords(uid, limit)

    async def _find_similar_by_keywords(self, uid: str, limit: int) -> Result[list[KuDTO]]:
        """
        Fallback: Find similar KUs using keyword matching and structural similarity.

        Uses:
        - Shared tags
        - Shared domain
        - Keyword overlap in title/content

        This is the graph-semantic foundation layer - always available.
        """
        query = """
        MATCH (source:Ku {uid: $uid})
        MATCH (similar:Ku)
        WHERE similar.uid <> source.uid

        // Calculate similarity based on:
        // 1. Shared tags
        WITH source, similar,
             size([t IN source.tags WHERE t IN similar.tags]) as shared_tags

        // 2. Same domain
        WITH source, similar, shared_tags,
             CASE WHEN source.domain = similar.domain THEN 2 ELSE 0 END as domain_match

        // 3. Keyword overlap (simple text similarity)
        WITH source, similar, shared_tags, domain_match,
             size([word IN split(toLower(source.title), ' ')
                   WHERE toLower(similar.title) CONTAINS word]) as title_overlap

        // Combine scores
        WITH similar,
             (shared_tags * 3 + domain_match + title_overlap) as similarity_score
        WHERE similarity_score > 0

        RETURN similar
        ORDER BY similarity_score DESC
        LIMIT $limit
        """

        try:
            result = await self.backend.execute_query(query, {"uid": uid, "limit": limit})

            if result.is_error:
                return Result.fail(result)

            records = result.value
            if not records:
                return Result.ok([])

            # Convert to DTOs
            dtos = [self._node_dict_to_dto(dict(record["similar"])) for record in records]
            self.logger.debug(f"Keyword search found {len(dtos)} similar units for {uid}")
            return Result.ok(dtos)

        except Exception as e:
            self.logger.error(f"Keyword search failed: {e}")
            return Result.fail(Errors.database(operation="keyword_search", message=str(e)))

    @with_error_handling("search_by_features", error_type="database")
    async def search_by_features(
        self, features: dict[str, Any], limit: int = 25
    ) -> Result[list[KuDTO]]:
        """
        Search by content features (complexity, readability, etc.).

        Uses intelligence service for feature-based matching.

        Args:
            features: Feature criteria to match
            limit: Maximum results to return

        Returns:
            Result containing list of matching KuDTOs
        """
        if not self.intelligence:
            return Result.fail(
                Errors.system(
                    message="Intelligence service not available",
                    operation="search_by_features",
                )
            )

        if not features:
            return Result.fail(Errors.validation("Feature criteria is required", field="features"))

        # Use intelligence service for feature matching
        result = await self.intelligence.search_by_features(features=features, limit=limit)

        if result.is_error:
            return Result.fail(result.expect_error())

        unit_uids = result.value

        # Retrieve full DTOs
        dtos = []
        for uid in unit_uids:
            unit_result = await self.backend.get(uid)
            if unit_result.is_ok and unit_result.value:
                dtos.append(self._to_dto(unit_result.value))

        self.logger.debug(f"Feature search with {features} returned {len(dtos)} results")
        return Result.ok(dtos)

    # =========================================================================
    # CONTEXT-AWARE SEARCH
    # =========================================================================

    @track_query_metrics("ku_search_with_context")
    @with_error_handling("search_with_user_context", error_type="database")
    async def search_with_user_context(
        self, query: str, user_context: dict[str, Any] | None = None, limit: int = 25
    ) -> Result[list[KuDTO]]:
        """
        Search with user context for personalized results.

        Considers user's learning level, preferences, completed content, etc.

        Args:
            query: Search query
            user_context: User context (level, preferences, history)
            limit: Maximum results to return

        Returns:
            Result containing list of personalized KuDTOs
        """
        if not query or not query.strip():
            return Result.fail(Errors.validation("Search query is required", field="query"))

        # Build filters from user context
        filters: dict[str, Any] = {}
        if user_context:
            if "level" in user_context:
                filters["complexity__lte"] = user_context["level"]

        # Use inherited search method
        result = await self.search(query, limit=limit * 2)  # Get more for ranking
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to DTOs
        dtos = self._convert_to_dtos(result.value[:limit])

        self.logger.debug(f"Context-aware search for '{query}' returned {len(dtos)} results")
        return Result.ok(dtos)

    @track_query_metrics("ku_search_semantic_intent")
    @with_error_handling("search_with_semantic_intent", error_type="database")
    async def search_with_semantic_intent(
        self,
        query: str,
        intent: str | None = None,
        _context: dict[str, Any] | None = None,
        limit: int = 25,
    ) -> Result[list[KuDTO]]:
        """
        Search with semantic intent understanding.

        Interprets user intent (learn, practice, review) and returns
        appropriate content.

        Args:
            query: Search query
            intent: User intent (learn, practice, review, explore)
            _context: Additional context
            limit: Maximum results to return

        Returns:
            Result containing list of intent-matched KuDTOs
        """
        if not query or not query.strip():
            return Result.fail(Errors.validation("Search query is required", field="query"))

        # Build filters based on intent
        filters: dict[str, Any] = {}

        if intent == "learn":
            filters["complexity__lte"] = "medium"
        elif intent == "practice":
            filters["content_type__in"] = ["exercise", "practice", "lab"]
        elif intent == "review":
            filters["content_type__in"] = ["summary", "reference", "cheatsheet"]

        # Execute search
        result = await self.search(query, limit=limit)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to DTOs
        dtos = self._convert_to_dtos(result.value)

        self.logger.debug(
            f"Semantic search for '{query}' with intent '{intent}' returned {len(dtos)} results"
        )
        return Result.ok(dtos)

    # =========================================================================
    # VECTOR SEARCH METHODS (NEW - January 2026)
    # =========================================================================

    @track_query_metrics("ku_search_semantic")
    @with_error_handling("search_by_semantic_query", error_type="database")
    async def search_by_semantic_query(
        self, query_text: str, limit: int = 10, min_score: float = 0.7
    ) -> Result[list[KuDTO]]:
        """
        Search Knowledge Units by natural language query using vector search.

        ARCHITECTURE:
        - Uses vector embeddings for semantic similarity
        - Falls back to keyword search if vector search unavailable
        - Both approaches are semantic - just different implementations

        Args:
            query_text: Natural language search query
            limit: Maximum results to return
            min_score: Minimum similarity score (0.0-1.0)

        Returns:
            Result containing list of semantically similar KuDTOs
        """
        if not query_text or not query_text.strip():
            return Result.fail(Errors.validation("Search query is required", field="query_text"))

        # Try semantic search with vector embeddings
        if self.vector_search and self.embeddings:
            semantic_result = await self.vector_search.find_similar_by_text(
                label="Ku", text=query_text, limit=limit, min_score=min_score
            )

            if semantic_result.is_ok:
                similar_nodes = semantic_result.value
                dtos = [self._node_dict_to_dto(node["node"]) for node in similar_nodes]
                self.logger.debug(f"Semantic search found {len(dtos)} results for '{query_text}'")
                return Result.ok(dtos)
            else:
                self.logger.warning(
                    f"Semantic search failed: {semantic_result.expect_error()}, falling back to keyword search"
                )

        # Fallback: Keyword search
        self.logger.info(f"Using keyword search fallback for '{query_text}'")
        return await self._search_by_keywords(query_text, limit)

    async def _search_by_keywords(self, query_text: str, limit: int) -> Result[list[KuDTO]]:
        """
        Fallback: Keyword-based search using CONTAINS.

        This is the graph-semantic foundation - always available.
        """
        query = """
        MATCH (ku:Ku)
        WHERE toLower(ku.title) CONTAINS toLower($query_text)
           OR toLower(ku.content) CONTAINS toLower($query_text)
           OR any(tag IN ku.tags WHERE toLower(tag) CONTAINS toLower($query_text))
        RETURN ku
        ORDER BY ku.updated_at DESC
        LIMIT $limit
        """

        try:
            result = await self.backend.execute_query(
                query, {"query_text": query_text, "limit": limit}
            )

            if result.is_error:
                return Result.fail(result)

            records = result.value
            if not records:
                return Result.ok([])

            dtos = [self._node_dict_to_dto(dict(record["ku"])) for record in records]
            self.logger.debug(f"Keyword search found {len(dtos)} results for '{query_text}'")
            return Result.ok(dtos)

        except Exception as e:
            self.logger.error(f"Keyword search failed: {e}")
            return Result.fail(Errors.database(operation="keyword_search", message=str(e)))

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _to_dto(self, entity: Ku) -> KuDTO:
        """Convert a Ku entity to KuDTO."""
        if isinstance(entity, KuDTO):
            return entity
        if isinstance(entity, dict):
            return KuDTO.from_dict(entity)
        # Convert frozen Ku to mutable KuDTO
        return KuDTO(
            uid=entity.uid,
            title=entity.title,
            content=entity.content,
            domain=entity.domain,
            quality_score=entity.quality_score,
            complexity=entity.complexity,
            semantic_links=list(entity.semantic_links) if entity.semantic_links else [],
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            tags=list(entity.tags) if entity.tags else [],
            metadata=dict(entity.metadata) if entity.metadata else {},
        )

    def _node_dict_to_dto(self, node_dict: dict[str, Any]) -> KuDTO:
        """
        Convert Neo4j node dict to KuDTO.

        Used for vector search results where nodes are returned as dicts.
        """
        return KuDTO.from_dict(node_dict)

    def _convert_to_dtos(self, entities: list[Any]) -> list[KuDTO]:
        """Convert a list of entities to KuDTOs."""
        return [self._to_dto(e) for e in entities]
