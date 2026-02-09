"""
LS Search Service - BaseService Pattern
========================================

Search operations for Learning Steps extending BaseService for
unified search architecture.

This service provides:
- Text search on title/intent/description (inherited from BaseService)
- Graph-aware faceted search with relationship traversal
- LS-specific methods: get_for_learning_path(), get_standalone_steps()

Architecture (January 2026 Unified):
- Extends BaseService[BackendOperations[Ls], Ls]
- Inherits: search(), get_by_status(), get_by_domain(), get_with_content(), etc.
- Adds: LS-specific methods for learning path integration
- No wrapper backend - uses UniversalNeo4jBackend directly
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.ls import Ls, StepDifficulty, StepStatus
from core.models.ls.ls_dto import LearningStepDTO
from core.models.search.query_parser import ParsedSearchQuery
from core.models.enums import Domain
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.protocols import BackendOperations  # noqa: F401
    from core.services.user import UserContext

logger = get_logger(__name__)


class LsSearchService(BaseService["BackendOperations[Ls]", Ls]):
    """
    Search service for Learning Steps - BaseService pattern.

    Implements DomainSearchOperations[Ls] protocol for integration with
    SearchRouter and unified search infrastructure.

    Inherited Methods (from BaseService):
    - search(query, limit) - Text search on _search_fields
    - get_by_relationship(related_uid, relationship_type, direction)
    - get_by_status(status, limit) - Filter by StepStatus
    - get_by_domain(domain, limit) - Filter by Domain
    - graph_aware_faceted_search(request) - Rich graph context search
    - get_with_content(uid) - Entity with full content
    - get_with_context(uid, depth) - Entity with graph neighborhood
    - get_prerequisites(uid, depth) - Prerequisite chain
    - get_enables(uid, depth) - What this enables
    - get_hierarchy(uid) - Position in KU → LS → LP hierarchy
    - get_user_progress(user_uid, entity_uid) - User mastery data

    LS-Specific Methods:
    - get_for_learning_path(path_uid) - Steps in a specific learning path
    - get_standalone_steps() - Steps not in any learning path
    - get_prioritized(user_uid, context) - Context-aware prioritization
    - intelligent_search(query) - NLP-enhanced search with filter extraction

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - Returns Result[T] for error handling
    - No custom filter classes - uses SearchRequest
    """

    # =========================================================================
    # DomainConfig consolidation (January 2026 Phase 3)
    # =========================================================================
    # All configuration in one place, using centralized relationship registry
    # See: /docs/decisions/ADR-025-service-consolidation-patterns.md
    _config = create_curriculum_domain_config(
        dto_class=LearningStepDTO,
        model_class=Ls,
        domain_name="ls",
        search_fields=("title", "intent", "description"),  # LS-specific fields
        search_order_by="updated_at",
        content_field="description",  # LS stores content in description
    )

    # =========================================================================
    # ABSTRACT METHOD IMPLEMENTATION
    # =========================================================================

    def _get_content_query(self) -> str:
        """
        Return Cypher query fragment for fetching LS content.

        For Learning Steps, content is stored inline in the description field.
        No separate content storage is used.
        """
        return """
        RETURN n, n.description as content
        """

    # =========================================================================
    # LS-SPECIFIC METHODS
    # =========================================================================

    async def get_for_learning_path(self, path_uid: str, limit: int = 100) -> Result[list[Ls]]:
        """
        Get Learning Steps belonging to a specific learning path.

        Steps are returned ordered by their sequence within the path.

        Args:
            path_uid: Learning path UID
            limit: Maximum results (default 100)

        Returns:
            Result containing Learning Steps in the path, ordered by sequence
        """
        if not path_uid:
            return Result.fail(Errors.validation(message="path_uid is required", field="path_uid"))

        # Use backend method if available
        backend_method = getattr(self.backend, "get_path_steps", None)
        if backend_method:
            return await backend_method(path_uid, limit)

        # Fallback to direct query
        from core.utils.neo4j_mapper import from_neo4j_node

        cypher = """
            MATCH (lp:Lp {uid: $path_uid})-[:HAS_STEP]->(ls:Ls)
            RETURN ls
            ORDER BY ls.sequence ASC
            LIMIT $limit
        """

        result = await self.backend.execute_query(cypher, {"path_uid": path_uid, "limit": limit})
        if result.is_error:
            return Result.fail(result.expect_error())

        steps = [from_neo4j_node(record["ls"], Ls) for record in result.value]

        self.logger.debug(f"Found {len(steps)} steps for path {path_uid}")
        return Result.ok(steps)

    async def get_standalone_steps(self, limit: int = 50) -> Result[list[Ls]]:
        """
        Get standalone Learning Steps (not part of any learning path).

        Args:
            limit: Maximum results (default 50)

        Returns:
            Result containing standalone Learning Steps
        """
        from core.utils.neo4j_mapper import from_neo4j_node

        cypher = """
            MATCH (ls:Ls)
            WHERE NOT (ls)<-[:HAS_STEP]-(:Lp)
            RETURN ls
            ORDER BY ls.updated_at DESC
            LIMIT $limit
        """

        result = await self.backend.execute_query(cypher, {"limit": limit})
        if result.is_error:
            return Result.fail(result.expect_error())

        steps = [from_neo4j_node(record["ls"], Ls) for record in result.value]

        self.logger.debug(f"Found {len(steps)} standalone steps")
        return Result.ok(steps)

    async def get_by_knowledge(self, ku_uid: str, limit: int = 20) -> Result[list[Ls]]:
        """
        Find learning steps that contain/teach this knowledge.

        Complementary to KuGraphService.find_learning_steps_containing().
        Returns full LS entities instead of just UIDs.

        Graph Pattern: (Ls)-[:CONTAINS_KNOWLEDGE]->(Ku)

        Args:
            ku_uid: Knowledge unit UID
            limit: Maximum results to return (default 20)

        Returns:
            Result containing list of Learning Step entities
        """
        if not ku_uid:
            return Result.fail(Errors.validation(message="ku_uid is required", field="ku_uid"))

        from core.utils.neo4j_mapper import from_neo4j_node

        cypher = """
            MATCH (ku:Ku {uid: $ku_uid})<-[:CONTAINS_KNOWLEDGE]-(ls:Ls)
            RETURN ls
            ORDER BY ls.sequence ASC
            LIMIT $limit
        """

        result = await self.backend.execute_query(cypher, {"ku_uid": ku_uid, "limit": limit})
        if result.is_error:
            return Result.fail(result.expect_error())

        steps = [from_neo4j_node(record["ls"], Ls) for record in result.value]

        self.logger.debug(f"Found {len(steps)} learning steps for knowledge {ku_uid}")
        return Result.ok(steps)

    async def get_prioritized(
        self, user_uid: str, context: UserContext, limit: int = 20
    ) -> Result[list[Ls]]:
        """
        Get Learning Steps prioritized by user context.

        Prioritization considers:
        1. In-progress steps (highest)
        2. Steps aligned with user's current goals
        3. Priority level
        4. Recently updated

        Args:
            user_uid: User UID for personalization
            context: User's context for goal alignment
            limit: Maximum results (default 20)

        Returns:
            Result containing prioritized Learning Steps
        """
        from core.utils.neo4j_mapper import from_neo4j_node

        # Build prioritization query
        cypher = """
            MATCH (ls:Ls)
            OPTIONAL MATCH (u:User {uid: $user_uid})-[progress:STUDYING]->(ls)
            RETURN ls, progress
            ORDER BY
                CASE
                    WHEN progress IS NOT NULL THEN 0
                    ELSE 1
                END,
                CASE ls.status
                    WHEN 'in_progress' THEN 0
                    WHEN 'not_started' THEN 1
                    ELSE 2
                END,
                CASE ls.priority
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                    ELSE 4
                END,
                ls.updated_at DESC
            LIMIT $limit
        """

        result = await self.backend.execute_query(cypher, {"user_uid": user_uid, "limit": limit})
        if result.is_error:
            return Result.fail(result.expect_error())

        steps = [from_neo4j_node(record["ls"], Ls) for record in result.value]

        self.logger.debug(f"Prioritized LS search returned {len(steps)} results")
        return Result.ok(steps)

    async def intelligent_search(
        self, query: str, limit: int = 50
    ) -> Result[tuple[list[Ls], ParsedSearchQuery]]:
        """
        Natural language search with automatic semantic filter extraction.

        Parses the query to extract:
        - Domain keywords: "tech", "health", "business"
        - Difficulty: "easy", "moderate", "challenging"
        - Status: "completed", "in progress"

        Args:
            query: Natural language search query
            limit: Maximum results (default 50)

        Returns:
            Result containing tuple of (matching Learning Steps, parsed query)
        """
        # Parse query for semantic filters
        parsed = self._parse_search_query(query)

        # Check for difficulty keywords
        difficulty: StepDifficulty | None = None
        query_lower = query.lower()

        difficulty_map = {
            "trivial": StepDifficulty.TRIVIAL,
            "easy": StepDifficulty.EASY,
            "moderate": StepDifficulty.MODERATE,
            "challenging": StepDifficulty.CHALLENGING,
            "advanced": StepDifficulty.ADVANCED,
        }
        for keyword, diff in difficulty_map.items():
            if keyword in query_lower:
                difficulty = diff
                break

        # Check for status keywords
        status: StepStatus | None = None
        if "completed" in query_lower:
            status = StepStatus.COMPLETED
        elif "in progress" in query_lower or "started" in query_lower:
            status = StepStatus.IN_PROGRESS
        elif "not started" in query_lower:
            status = StepStatus.NOT_STARTED

        # Build filters dict for find_by
        filters: dict[str, object] = {}
        if parsed.domains:
            filters["domain"] = parsed.domains[0].value
        if difficulty:
            filters["difficulty"] = difficulty.value
        if status:
            filters["status"] = status.value

        # Execute search with filters
        if filters:
            result = await self.backend.find_by(limit=limit, **filters)
        else:
            result = await self.search(parsed.text_query, limit=limit)

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok((result.value, parsed))

    def _parse_search_query(self, query: str) -> ParsedSearchQuery:
        """
        Parse natural language query for semantic filters.

        Extracts:
        - Domain from keywords
        - Remaining text query
        """
        query_lower = query.lower()
        words = query_lower.split()

        # Domain detection
        domain: Domain | None = None
        domain_keywords = {
            "tech": Domain.TECH,
            "technology": Domain.TECH,
            "health": Domain.HEALTH,
            "wellness": Domain.HEALTH,
            "business": Domain.BUSINESS,
            "personal": Domain.PERSONAL,
            "finance": Domain.FINANCE,
            "learning": Domain.LEARNING,
        }

        remaining_words = []
        for word in words:
            if word in domain_keywords and domain is None:
                domain = domain_keywords[word]
            else:
                remaining_words.append(word)

        text_query = " ".join(remaining_words) if remaining_words else query

        return ParsedSearchQuery(
            raw_query=query,
            text_query=text_query,
            domains=(domain,) if domain else (),
        )
