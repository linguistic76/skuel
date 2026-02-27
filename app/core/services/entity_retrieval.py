"""
Unified Knowledge Retrieval Service
====================================

**UTILITY SERVICE** - Injected dependency, not a standalone service.
This is THE single retrieval service used BY search routes and personalized discovery, not a duplicate.

Combines vector search, graph traversal, and intelligent ranking into one unified interface.
Provides hybrid search (embeddings + graph structure) with user context awareness.

Following SKUEL principle: One way forward - no alternatives, no backwards compatibility.

Architecture:
- Lives at `/core/services/` level (not in `/ku/` directory)
- Injected into search routes, personalized discovery adapter
- Specialized utility for multi-strategy knowledge retrieval
- See `/core/services/ku/README.md` for architecture overview
"""

from dataclasses import dataclass
from operator import attrgetter
from typing import Any, Protocol, runtime_checkable

from core.constants import GraphDepth
from core.models.curriculum.curriculum import Curriculum
from core.models.query import (
    IndexStrategy,
    QueryElements,
    QueryIntent,
    analyze_query_intent,
    create_search_request,
)

# Use protocol interfaces instead of ports
from core.ports.curriculum_protocols import KuOperations
from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService
from core.services.user import UserContext
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_final_score


@runtime_checkable
class KuSearchCriteria(Protocol):
    """Search criteria for knowledge units."""

    query: str
    limit: int
    filters: dict


@dataclass
class KuSearchCriteriaImpl:
    """Concrete implementation of KuSearchCriteria."""

    query: str
    limit: int
    filters: dict


@runtime_checkable
class KuSearchResult(Protocol):
    """Search result for knowledge units."""

    items: list


logger = get_logger(__name__)


@dataclass
class EnhancedResult:
    """A knowledge unit with retrieval enhancements"""

    unit: Curriculum
    base_score: float  # Original search score
    vector_score: float  # Semantic similarity score
    graph_score: float  # Graph relevance score
    final_score: float  # Combined score
    graph_context: dict[str, Any]  # Related nodes, paths
    explanation: str  # Why this was retrieved


@dataclass
class EntityRetrievalResult:
    """Complete retrieval result with all enhancements"""

    results: list[EnhancedResult]
    query_analysis: QueryElements  # Use unified QueryElements
    total_found: int
    retrieval_time_ms: int


class EntityRetrieval:
    """
    THE single retrieval service for SKUEL.
    Unifies vector search, graph traversal, and intelligent ranking.

    This is not optional - all knowledge retrieval goes through this service.
    """

    def __init__(
        self,
        knowledge_repo: KuOperations,
        embeddings_service: Neo4jGenAIEmbeddingsService | None = None,
        unified_query_builder=None,  # Use the unified query builder service
        user_progress_service=None,  # Optional progress service for intelligent ranking
        chunking_service=None,  # Optional chunking service for RAG
    ) -> None:
        """
        Initialize with required services. Embeddings service is optional.

        Args:
            knowledge_repo: Repository for knowledge operations (required),
            embeddings_service: Service for vector operations (optional - falls back to keyword search),
            unified_query_builder: THE query builder service (required),
            user_progress_service: Optional UserProgressService for progress-aware ranking,
            chunking_service: Optional chunking service for chunk-based RAG retrieval

        Raises:
            ValueError: If any required service is missing
        """
        if not knowledge_repo:
            raise ValueError("Knowledge repository is required - no fallback")
        if not unified_query_builder:
            raise ValueError(
                "Unified query builder is required - graph operations are not optional"
            )

        self.repo = knowledge_repo
        self.embeddings = embeddings_service  # Can be None - graceful degradation
        self.query_builder = unified_query_builder
        self.user_progress = user_progress_service
        self.chunking_service = chunking_service

        features = []
        if embeddings_service:
            features.append("vector search")
        else:
            features.append("keyword search fallback (no embeddings)")
        if chunking_service:
            features.append("chunk-based RAG")
        if user_progress_service:
            features.append("progress-aware ranking")

        logger.info(f"✅ EntityRetrieval initialized with {', '.join(features)}")

    async def retrieve(
        self, query: str, context: UserContext | None = None, limit: int = 10
    ) -> Result[EntityRetrievalResult]:
        """
        THE way to retrieve knowledge. All retrieval goes through this method.

        Pipeline:
        1. Build optimized query using unified query builder
        2. Analyze query intent
        3. Execute base search
        4. Enhance with graph context
        5. Add vector similarity
        6. Rank and filter results

        Args:
            query: User's search query,
            context: Optional user context for personalization,
            limit: Maximum results to return

        Returns:
            Result containing retrieval results or error
        """
        try:
            import time

            start_time = time.time()

            # Step 1: Build optimized query request using unified builder
            create_search_request(labels=["Entity"], search_text=query, limit=limit * 2)

            # Step 2: Analyze query intent (no branching - always done)
            query_analysis = self._analyze_query_intent(query)

            # Step 3: Check if chunking service is available for RAG retrieval
            if self.chunking_service:
                # Use chunk-based search for better RAG retrieval
                base_results = await self._execute_chunk_search(query, query_analysis, limit * 2)
            else:
                # Fallback to standard search
                base_results = await self._execute_base_search(query_analysis, query, limit * 2)

            if not base_results:
                # Return empty result, not an error
                return Result.ok(
                    EntityRetrievalResult(
                        results=[],
                        query_analysis=query_analysis,
                        total_found=0,
                        retrieval_time_ms=int((time.time() - start_time) * 1000),
                    )
                )

            # Step 4: Enhance with graph context (always done)
            graph_enhanced = await self._add_graph_context(base_results, query_analysis)

            # Step 5: Add vector similarity (always done)
            vector_enhanced = await self._add_vector_similarity(graph_enhanced, query)

            # Step 6: Rank and filter with progress-aware intelligence (always done)
            final_results = await self._rank_and_filter(
                vector_enhanced, context, query_analysis, limit
            )

            retrieval_time = int((time.time() - start_time) * 1000)

            return Result.ok(
                EntityRetrievalResult(
                    results=final_results,
                    query_analysis=query_analysis,
                    total_found=len(final_results),
                    retrieval_time_ms=retrieval_time,
                )
            )

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return Result.fail(Errors.system(message=str(e), operation="retrieve"))

    def _analyze_query_intent(self, query: str) -> QueryElements:
        """
        Analyze query to understand intent and requirements.
        Uses the unified query analysis from query_models.
        """
        # Use the unified analyze function
        # Add context-based filters
        # Note: current_domain_uid removed from UserContext
        # Could use primary_goal_focus domain if needed in future

        return analyze_query_intent(query)

    async def _execute_chunk_search(
        self, query: str, analysis: QueryElements, limit: int
    ) -> list[EnhancedResult]:
        """
        Execute chunk-based search for superior RAG retrieval.
        Searches within content chunks rather than full documents.
        """
        try:
            # Search across chunks
            chunk_results = await self.chunking_service.search_chunks(
                query=query,
                knowledge_uids=None,  # Search all knowledge
                limit=limit,
            )

            if not chunk_results.is_ok or not chunk_results.value:
                return []

            # Group chunks by knowledge unit and build enhanced results
            ku_chunks = {}
            for chunk_match in chunk_results.value:
                uid = chunk_match["knowledge_uid"]
                if uid not in ku_chunks:
                    ku_chunks[uid] = []
                ku_chunks[uid].append(chunk_match)

            enhanced_results = []
            for uid, chunks in ku_chunks.items():
                # Get the knowledge unit
                unit_result = await self.repo.get_ku(uid)
                if unit_result.is_error or not unit_result.value:
                    continue

                # Get content metadata for advanced scoring
                metadata_result = await self.chunking_service.get_metadata(uid)

                # Calculate aggregate relevance from chunks
                chunk_scores = [c["relevance_score"] for c in chunks]
                avg_chunk_score = sum(chunk_scores) / len(chunk_scores) if chunk_scores else 0.5

                # Use metadata for additional relevance scoring
                metadata_score = 0.5
                if metadata_result.is_ok:
                    metadata = metadata_result.value
                    metadata_score = metadata.search_relevance_score(query)

                # Combine scores
                base_score = (avg_chunk_score + metadata_score) / 2

                # Create explanation based on matching chunks
                chunk_types = set(c["chunk"]["chunk_type"] for c in chunks[:3])
                explanation = f"Found {len(chunks)} matching chunks ({', '.join(chunk_types)})"

                enhanced = EnhancedResult(
                    unit=unit_result.value,
                    base_score=base_score,
                    vector_score=0.0,  # Will be added in vector enhancement
                    graph_score=0.0,  # Will be added in graph enhancement
                    final_score=base_score,
                    graph_context={"matching_chunks": len(chunks)},
                    explanation=explanation,
                )
                enhanced_results.append(enhanced)

            # Sort by base score
            enhanced_results.sort(key=attrgetter("base_score"), reverse=True)

            logger.info(f"Chunk search found {len(enhanced_results)} knowledge units from chunks")
            return enhanced_results[:limit]

        except Exception as e:
            logger.error(f"Chunk search failed: {e}")
            # Fallback to base search
            return await self._execute_base_search(analysis, query, limit)

    async def _execute_base_search(
        self, _analysis: QueryElements, query: str, limit: int
    ) -> list[EnhancedResult]:
        """
        Execute base search using repository.
        Always returns EnhancedResult objects for consistency.
        """
        # Execute text search
        search_result = await self.repo.search(query, limit)

        if search_result.is_error or not search_result.value:
            logger.warning(
                f"Base search failed or empty: {search_result.error if search_result.is_error else 'no results'}"
            )
            return []

        # Convert to EnhancedResult objects
        enhanced_results = []
        for item in search_result.value:
            enhanced = EnhancedResult(
                unit=item,
                base_score=1.0,  # Will be updated
                vector_score=0.0,  # Will be calculated
                graph_score=0.0,  # Will be calculated
                final_score=0.0,  # Will be calculated
                graph_context={},  # Will be populated
                explanation=f"Matched query: {query}",
            )
            enhanced_results.append(enhanced)

        return enhanced_results

    async def _add_graph_context(
        self, results: list[EnhancedResult], analysis: QueryElements
    ) -> list[EnhancedResult]:
        """
        Enhance results with graph context.
        This is always done - graph context is not optional.
        """
        for result in results:
            # Use unified query builder to generate graph context query
            if analysis.intent:
                context_query = self.query_builder.build_graph_context_query(
                    node_uid=result.unit.uid, intent=analysis.intent, depth=analysis.depth_required
                )
            else:
                # Default intent if not analyzed
                context_query = self.query_builder.build_graph_context_query(
                    node_uid=result.unit.uid,
                    intent=QueryIntent.EXPLORATORY,
                    depth=GraphDepth.NEIGHBORHOOD,
                )

            # Execute query (would need actual Neo4j connection here)
            # For now, populate with structured context
            result.graph_context = {
                "depth_explored": analysis.depth_required,
                "relationships_found": True,
                "query_type": analysis.intent.value if analysis.intent else "exploratory",
                "query": context_query,  # Store the generated query for transparency
            }

            # Calculate graph score based on connectivity
            result.graph_score = self._calculate_graph_score(result.graph_context)

        return results

    async def _add_vector_similarity(
        self, results: list[EnhancedResult], query: str
    ) -> list[EnhancedResult]:
        """
        Add vector similarity scores using embeddings service.
        Falls back to keyword search if embeddings unavailable (GENAI_FALLBACK_TO_KEYWORD_SEARCH=true).
        """
        # Check if embeddings service is available
        if not self.embeddings:
            logger.info("Embeddings service unavailable - skipping vector similarity scoring")
            # Set all vector scores to 0.0 (keyword search will be used)
            for result in results:
                result.vector_score = 0.0
            return results

        # Get query embedding
        query_embedding = await self.embeddings.create_embedding(query)

        if not query_embedding:
            logger.error("Failed to create query embedding")
            # Don't fail, but scores remain at 0
            return results

        for result in results:
            # Get or create content embedding
            content_text = f"{result.unit.title} {result.unit.content}"
            content_embedding = await self.embeddings.create_embedding(content_text)

            if content_embedding:
                # Calculate cosine similarity
                result.vector_score = self.embeddings.calculate_similarity(
                    query_embedding, content_embedding
                )
            else:
                result.vector_score = 0.0

        return results

    async def _rank_and_filter(
        self,
        results: list[EnhancedResult],
        context: UserContext | None,
        query_elements: QueryElements,
        limit: int,
    ) -> list[EnhancedResult]:
        """
        Final ranking and filtering of results with progress-aware intelligence.

        This is where the intelligence loop closes - user progress directly
        influences ranking to surface the most relevant knowledge based on
        their learning state.
        """
        # Get user progress profile if available
        user_profile = None
        if self.user_progress and context and context.user_uid:
            profile_result = await self.user_progress.build_user_knowledge_profile(context.user_uid)
            if profile_result.is_ok:
                user_profile = profile_result.value
                logger.debug(
                    f"🧠 Progress-aware ranking: "
                    f"{len(user_profile.mastered_uids)} mastered, "
                    f"{len(user_profile.in_progress_uids)} in-progress"
                )

        # Calculate final scores
        for result in results:
            # Weighted combination of base scores
            result.final_score = (
                result.base_score * 0.3 + result.vector_score * 0.4 + result.graph_score * 0.3
            )

            # Apply context boost (domain/level)
            if context:
                context_boost = self._calculate_context_boost(result, context)
                result.final_score *= context_boost

            # Apply progress-aware weights (THE intelligence loop)
            if user_profile:
                progress_boost = self._calculate_progress_boost(
                    result, user_profile, query_elements
                )
                result.final_score *= progress_boost
                logger.debug(
                    f"  {result.unit.uid[:20]}: "
                    f"base={result.final_score:.2f} → "
                    f"progress_boost={progress_boost:.2f}"
                )

        # Sort by final score
        results.sort(key=get_final_score, reverse=True)

        # Return top N
        return results[:limit]

    def _calculate_graph_score(self, graph_context: dict[str, Any]) -> float:
        """Calculate score based on graph connectivity and relevance"""
        # Simple scoring based on graph properties
        score = 0.5  # Base score

        if graph_context.get("relationships_found"):
            score += 0.3

        if graph_context.get("depth_explored", 0) > 1:
            score += 0.2

        return min(score, 1.0)

    def _calculate_context_boost(self, result: EnhancedResult, context: UserContext) -> float:
        """Calculate boost factor based on user context"""
        boost = 1.0

        # Boost if in user's current domain
        # Note: current_domain_uid removed from UserContext
        # Could use primary_goal_focus or learning_velocity_by_domain in future

        # Boost based on user's learning level match (curriculum entities only)
        unit_learning_level = getattr(result.unit, "learning_level", None)
        if (
            context.learning_level
            and unit_learning_level
            and context.learning_level == unit_learning_level
        ):
            boost *= 1.1

        return boost

    def _calculate_progress_boost(
        self,
        result: EnhancedResult,
        user_profile,  # UserKnowledgeProfile from UserProgressService
        query_elements: QueryElements,
    ) -> float:
        """
        Calculate progress-aware boost factor.

        This is THE intelligence loop - user's learning state directly
        influences what knowledge surfaces.

        Boost strategy:
        - Demote already mastered (0.5x) - don't repeat what they know
        - Boost in-progress (1.2x) - continue active learning
        - Boost struggling for review intent (1.3x) - help where needed
        - De-boost struggling for new learning (0.8x) - don't overwhelm
        - Boost prerequisites-ready (1.4x) - maximize readiness
        - De-boost prerequisites-blocked (0.6x) - avoid frustration
        """
        boost = 1.0
        unit_uid = result.unit.uid

        # Already mastered - significantly demote
        if unit_uid in user_profile.mastered_uids:
            boost *= 0.5
            result.explanation += " [Already mastered]"
            return boost

        # Active in-progress - boost to support continuation
        if unit_uid in user_profile.in_progress_uids:
            boost *= 1.2
            result.explanation += " [In progress - continue learning]"

        # Struggling - context-aware boost/de-boost
        if unit_uid in user_profile.struggling_uids:
            if query_elements.intent == QueryIntent.PRACTICE:
                boost *= 1.3  # Boost for review/practice - this is what needs attention
                result.explanation += " [Struggling - review recommended]"
            else:
                boost *= 0.8  # De-boost for new learning - focus on gaps first
                result.explanation += " [Struggling - review needed before advancing]"

        # Prerequisites check - readiness matters
        prereq_status = self._check_prerequisites_readiness(result.unit, user_profile)

        if prereq_status == "ready":
            # Prerequisites satisfied but not started - perfect next step
            boost *= 1.4
            result.explanation += " [Prerequisites ready - ideal next step]"
        elif prereq_status == "blocked":
            # Missing prerequisites - de-boost to avoid frustration
            boost *= 0.6
            result.explanation += " [Prerequisites not yet met]"

        # Needs review - gentle boost
        if unit_uid in user_profile.needs_review_uids:
            boost *= 1.1
            result.explanation += " [Review recommended]"

        return boost

    def _check_prerequisites_readiness(
        self,
        unit,  # Knowledge unit
        user_profile,
    ) -> str:
        """
        Check if user is ready for this knowledge unit.

        Returns:
            "ready" - prerequisites satisfied, user ready to start
            "blocked" - missing prerequisites
            "unknown" - can't determine (no prerequisite data)
        """
        unit_uid = unit.uid

        # If we have prerequisite data for this unit
        if unit_uid in user_profile.prerequisite_map:
            required_prereqs = user_profile.prerequisite_map[unit_uid]

            # Check if all prerequisites are completed
            if all(prereq in user_profile.completed_prerequisites for prereq in required_prereqs):
                return "ready"
            else:
                return "blocked"

        # No prerequisite data available
        return "unknown"

    async def retrieve_with_optimized_query(
        self, query: str, context: UserContext | None = None, limit: int = 10
    ) -> Result[EntityRetrievalResult]:
        """
        Retrieve knowledge using the unified query builder's optimization.

        This method demonstrates full integration with the unified query builder,
        using its optimization capabilities for the best performance.
        """
        try:
            import time

            time.time()

            # Build optimized query request
            search_req = create_search_request(
                labels=["Entity"], search_text=query, limit=limit * 2
            )

            # Use unified query builder to get optimized query plan
            optimization_result = await self.query_builder.build_optimized_query(search_req)
            if optimization_result.is_error:
                logger.warning(
                    f"Query optimization failed, falling back to standard retrieval: {optimization_result.error}"
                )
                return await self.retrieve(query, context, limit)

            optimized_plan = optimization_result.value.best_plan

            # Log optimization strategy for transparency
            logger.info(
                f"Using {optimized_plan.strategy.value} strategy: {optimized_plan.explanation}"
            )

            # Execute optimized query through repository
            # (Repository would need to support executing raw Cypher)
            # For now, fall back to standard retrieval with the insight from optimization

            # The optimized plan gives us insights we can use
            if optimized_plan.strategy == IndexStrategy.FULLTEXT_SEARCH:
                # Fulltext search is available, prioritize it
                logger.debug("Fulltext index available, using text-based retrieval")
            elif optimized_plan.strategy == IndexStrategy.VECTOR_SEARCH:
                # Vector search is available, prioritize semantic search
                logger.debug("Vector index available, prioritizing semantic retrieval")

            # Continue with standard retrieval enhanced by optimization insights
            return await self.retrieve(query, context, limit)

        except Exception as e:
            logger.error(f"Optimized retrieval failed: {e}")
            return Result.fail(
                Errors.system(message=str(e), operation="retrieve_with_optimized_query")
            )
