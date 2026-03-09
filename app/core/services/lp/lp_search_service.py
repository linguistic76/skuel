"""
LP Search Service - BaseService Pattern
========================================

Search operations for Learning Paths extending BaseService for
unified search architecture.

This service provides:
- Text search on name/goal/outcomes (inherited from BaseService)
- Graph-aware faceted search with relationship traversal
- LP-specific methods: get_by_path_type(), get_aligned_with_goal()

Architecture (January 2026 Unified):
- Extends BaseService[BackendOperations[Lp], Lp]
- Inherits: search(), get_by_status(), get_by_domain(), get_with_content(), etc.
- Adds: LP-specific methods for path type and goal alignment
- No wrapper backend - uses UniversalNeo4jBackend directly
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.enums import Domain
from core.models.enums.curriculum_enums import LpType
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.learning_path_dto import LearningPathDTO
from core.models.search.query_parser import ParsedSearchQuery
from core.services.base_service import BaseService
from core.services.domain_config import create_curriculum_domain_config
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import BackendOperations
    from core.services.user import UserContext

logger = get_logger(__name__)


class LpSearchService(BaseService["BackendOperations[LearningPath]", LearningPath]):
    """
    Search service for Learning Paths - BaseService pattern.

    Implements DomainSearchOperations[Lp] protocol for integration with
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
    - get_hierarchy(uid) - Position in KU → LS → LP hierarchy
    - get_user_progress(user_uid, entity_uid) - User mastery data

    LP-Specific Methods:
    - get_by_path_type(path_type) - Filter by LP type
    - list_by_creator(user_uid) - Paths created by user
    - get_aligned_with_goal(goal_uid) - Paths aligned with goal
    - get_prioritized(user_uid, context) - Context-aware prioritization
    - intelligent_search(query) - NLP-enhanced search with filter extraction

    SKUEL Architecture:
    - No custom filter classes - uses SearchRequest
    """

    # =========================================================================
    # DomainConfig consolidation (January 2026)
    # =========================================================================
    # All configuration in one place, using centralized relationship registry
    # See: /docs/decisions/ADR-025-service-consolidation-patterns.md
    # Note: LP uses name instead of title, and stores main content in goal field
    _config = create_curriculum_domain_config(
        dto_class=LearningPathDTO,
        model_class=LearningPath,
        entity_label="Entity",
        domain_name="lp",
        search_fields=("title", "description"),  # LP: name→title, goal→description
        search_order_by="updated_at",
        content_field="description",  # LP goal mapped to Entity description
    )

    def __init__(self, backend: BackendOperations[LearningPath]) -> None:
        """Initialize service with required backend."""
        super().__init__(backend=backend, service_name="lp.search")

    # =========================================================================
    # ABSTRACT METHOD IMPLEMENTATION
    # =========================================================================

    def _get_content_query(self) -> str:
        """
        Return Cypher query fragment for fetching LP content.

        For Learning Paths, content is stored in the goal and outcomes fields.
        """
        return """
        RETURN n, n.description as content, n.outcomes as outcomes
        """

    # =========================================================================
    # LP-SPECIFIC METHODS
    # =========================================================================

    async def get_by_path_type(
        self, path_type: LpType, limit: int = 50
    ) -> Result[list[LearningPath]]:
        """
        Get Learning Paths by path type.

        Args:
            path_type: LpType to filter by (STRUCTURED, ADAPTIVE, etc.)
            limit: Maximum results (default 50)

        Returns:
            Result containing Learning Paths of the specified type
        """
        from core.ports import get_enum_value

        return await self.backend.find_by(
            limit=limit,
            path_type=get_enum_value(path_type),
        )

    async def list_by_creator(self, user_uid: str, limit: int = 50) -> Result[list[LearningPath]]:
        """
        List Learning Paths created by a specific user.

        Args:
            user_uid: User UID who created the paths
            limit: Maximum results (default 50)

        Returns:
            Result containing Learning Paths created by the user
        """
        if not user_uid:
            return Result.fail(Errors.validation(message="user_uid is required", field="user_uid"))

        return await self.backend.find_by(
            limit=limit,
            created_by=user_uid,
        )

    async def get_aligned_with_goal(
        self, goal_uid: str, limit: int = 50
    ) -> Result[list[LearningPath]]:
        """
        Get Learning Paths aligned with a specific goal.

        Uses graph relationship traversal to find paths connected
        via ALIGNED_WITH_GOAL relationship.

        Args:
            goal_uid: Goal UID to find aligned paths for
            limit: Maximum results (default 50)

        Returns:
            Result containing Learning Paths aligned with the goal
        """
        if not goal_uid:
            return Result.fail(Errors.validation(message="goal_uid is required", field="goal_uid"))

        # Use backend method if available
        backend_method = getattr(self.backend, "get_aligned_goals", None)
        if backend_method:
            return await backend_method(goal_uid, limit)

        # Fallback to direct query
        from core.utils.neo4j_mapper import from_neo4j_node

        cypher = """
            MATCH (lp:Entity {entity_type: 'learning_path'})-[:ALIGNED_WITH_GOAL]->(g:Goal {uid: $goal_uid})
            RETURN lp
            ORDER BY lp.updated_at DESC
            LIMIT $limit
        """

        result = await self.backend.execute_query(cypher, {"goal_uid": goal_uid, "limit": limit})
        if result.is_error:
            return Result.fail(result.expect_error())

        paths = [from_neo4j_node(record["lp"], LearningPath) for record in result.value]

        self.logger.debug(f"Found {len(paths)} paths aligned with goal {goal_uid}")
        return Result.ok(paths)

    async def get_by_knowledge(self, ku_uid: str, limit: int = 20) -> Result[list[LearningPath]]:
        """
        Find learning paths that teach this knowledge (via learning steps).

        Complementary to ArticleGraphService.find_learning_paths_teaching().
        Returns full LP entities instead of just UIDs.

        Graph Pattern: (Ku{learning_path})-[:HAS_STEP]->(Ku{learning_step})-[:CONTAINS_KNOWLEDGE]->(Ku)

        This is a 2-hop indirect relationship query. Uses DISTINCT since
        multiple steps within a path may contain the same knowledge.

        Args:
            ku_uid: Knowledge unit UID
            limit: Maximum results to return (default 20)

        Returns:
            Result containing list of Learning Path entities
        """
        if not ku_uid:
            return Result.fail(Errors.validation(message="ku_uid is required", field="ku_uid"))

        from core.utils.neo4j_mapper import from_neo4j_node

        cypher = """
            MATCH (ku:Entity {uid: $ku_uid})<-[:CONTAINS_KNOWLEDGE]-(ls:Entity {entity_type: 'learning_step'})<-[:HAS_STEP]-(lp:Entity {entity_type: 'learning_path'})
            RETURN DISTINCT lp
            ORDER BY lp.created_at DESC
            LIMIT $limit
        """

        result = await self.backend.execute_query(cypher, {"ku_uid": ku_uid, "limit": limit})
        if result.is_error:
            return Result.fail(result.expect_error())

        paths = [from_neo4j_node(record["lp"], LearningPath) for record in result.value]

        self.logger.debug(f"Found {len(paths)} learning paths for knowledge {ku_uid}")
        return Result.ok(paths)

    async def get_with_steps(self, uid: str, limit: int = 100) -> Result[tuple[LearningPath, list]]:
        """
        Get Learning Path with its steps loaded.

        Args:
            uid: Learning Path UID
            limit: Maximum steps to load (default 100)

        Returns:
            Result containing tuple of (Learning Path, list of steps)
        """
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))

        # Get the path first
        path_result = await self.get(uid)
        if path_result.is_error:
            return Result.fail(path_result.expect_error())

        # Get steps via backend
        backend_method = getattr(self.backend, "get_steps", None)
        if backend_method:
            steps_result = await backend_method(uid, limit)
            if steps_result.is_error:
                return Result.fail(steps_result.expect_error())
            return Result.ok((path_result.value, steps_result.value))

        # Fallback - return empty steps
        return Result.ok((path_result.value, []))

    async def get_prioritized(
        self, user_uid: str, context: UserContext, limit: int = 20
    ) -> Result[list[LearningPath]]:
        """
        Get Learning Paths prioritized by user context.

        Prioritization considers:
        1. Adaptive paths (highest - personalized learning)
        2. Paths aligned with user's goals
        3. Structured paths
        4. Recently updated

        Args:
            user_uid: User UID for personalization
            context: User's context for goal alignment
            limit: Maximum results (default 20)

        Returns:
            Result containing prioritized Learning Paths
        """
        from core.utils.neo4j_mapper import from_neo4j_node

        # Build prioritization query
        cypher = """
            MATCH (lp:Entity {entity_type: 'learning_path'})
            OPTIONAL MATCH (u:User {uid: $user_uid})-[enrolled:ENROLLED_IN]->(lp)
            OPTIONAL MATCH (lp)-[:ALIGNED_WITH_GOAL]->(g:Goal)<-[:OWNS]-(u2:User {uid: $user_uid})
            WITH lp, enrolled, count(g) as goal_alignment
            RETURN lp
            ORDER BY
                CASE
                    WHEN enrolled IS NOT NULL THEN 0
                    ELSE 1
                END,
                goal_alignment DESC,
                CASE lp.path_type
                    WHEN 'adaptive' THEN 0
                    WHEN 'structured' THEN 1
                    WHEN 'accelerated' THEN 2
                    WHEN 'remedial' THEN 3
                    ELSE 4
                END,
                lp.updated_at DESC
            LIMIT $limit
        """

        result = await self.backend.execute_query(cypher, {"user_uid": user_uid, "limit": limit})
        if result.is_error:
            return Result.fail(result.expect_error())

        paths = [from_neo4j_node(record["lp"], LearningPath) for record in result.value]

        self.logger.debug(f"Prioritized LP search returned {len(paths)} results")
        return Result.ok(paths)

    async def intelligent_search(
        self, query: str, limit: int = 50
    ) -> Result[tuple[list[LearningPath], ParsedSearchQuery]]:
        """
        Natural language search with automatic semantic filter extraction.

        Parses the query to extract:
        - Domain keywords: "tech", "health", "business"
        - Path type: "structured", "adaptive", "exploratory"
        - Difficulty: "beginner", "intermediate", "advanced"

        Args:
            query: Natural language search query
            limit: Maximum results (default 50)

        Returns:
            Result containing tuple of (matching Learning Paths, parsed query)
        """
        # Parse query for semantic filters
        parsed = self._parse_search_query(query)

        # Check for path type keywords
        path_type: LpType | None = None
        query_lower = query.lower()

        path_type_map = {
            "structured": LpType.STRUCTURED,
            "adaptive": LpType.ADAPTIVE,
            "exploratory": LpType.EXPLORATORY,
            "remedial": LpType.REMEDIAL,
            "accelerated": LpType.ACCELERATED,
        }
        for keyword, pt in path_type_map.items():
            if keyword in query_lower:
                path_type = pt
                break

        # Check for difficulty keywords
        difficulty: str | None = None
        if "beginner" in query_lower:
            difficulty = "beginner"
        elif "intermediate" in query_lower:
            difficulty = "intermediate"
        elif "advanced" in query_lower:
            difficulty = "advanced"

        # Build filters dict for find_by
        from core.ports import get_enum_value

        filters: dict[str, object] = {}
        if parsed.domains:
            filters["domain"] = get_enum_value(parsed.domains[0])
        if path_type:
            filters["path_type"] = get_enum_value(path_type)
        if difficulty:
            filters["step_difficulty"] = difficulty

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
