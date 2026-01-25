"""
Principle Search Service - Search and Discovery Operations
============================================================

Handles search and discovery operations for principles.
Implements DomainSearchOperations[Principle] protocol plus principle-specific methods.

**Responsibilities:**
- Text search on name/statement/description
- Filter by status, domain/category, strength
- Time-based queries (needing review, recently adopted)
- Context-aware prioritization
- Graph-based relationship queries

**Pattern:**
This service follows the SearchService pattern documented in:
/docs/patterns/search_service_pattern.md

Version: 1.0.0
Date: 2025-11-28

Changelog:
- v1.0.0 (2025-11-28): Initial implementation extracted from PrinciplesService
  Implements DomainSearchOperations[Principle] protocol
"""

from datetime import date, timedelta

from core.models.principle.principle import (
    Principle,
    PrincipleCategory,
    PrincipleStrength,
)
from core.models.principle.principle_dto import PrincipleDTO
from core.models.relationship_names import RelationshipName
from core.models.search.query_parser import ParsedSearchQuery, SearchQueryParser
from core.models.shared_enums import Domain
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.protocols.domain_protocols import PrinciplesOperations
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result


class PrinciplesSearchService(BaseService[PrinciplesOperations, Principle]):
    """
    Principle search and discovery operations.

    Implements DomainSearchOperations[Principle] protocol for consistent
    search interface across all activity domains.

    Universal Methods (DomainSearchOperations protocol):
    - search() - Text search on name/statement/description (inherited from BaseService)
    - get_by_status() - Filter by is_active status
    - get_by_domain() - Filter by PrincipleCategory (mapped to Domain concept)
    - get_prioritized() - Context-aware prioritization
    - get_by_relationship() - Graph relationship queries
    - get_due_soon() - Principles needing review soon
    - get_overdue() - Principles past review date

    Principle-Specific Methods:
    - get_by_strength() - Filter by PrincipleStrength (core, strong, moderate, etc.)
    - get_by_category() - Filter by PrincipleCategory
    - get_guiding_goals() - Principles guiding specific goals
    - get_inspiring_habits() - Principles inspiring specific habits
    - get_for_choice() - Principles relevant to a decision
    - get_active_principles() - Get all active principles for user
    - list_categories() - Get all PrincipleCategory values
    - get_needing_review() - Principles past review threshold

    Semantic Types Used:
    - GUIDES_GOAL: Principle provides guidance for goal setting/achievement
    - INSPIRES_HABIT: Principle inspires habit formation/maintenance
    - GUIDES_CHOICE: Principle guides decision-making
    - RELATED_TO: Principle relates to another principle

    Source Tag: "principles_search_explicit"
    - Format: "principles_search_explicit" for user-defined relationships
    - Format: "principles_search_inferred" for system-discovered relationships

    Confidence Scoring:
    - 0.9+: User explicitly linked principle to goal/habit/choice
    - 0.7-0.9: Inferred from category/strength alignment
    - <0.7: Suggested based on content similarity

    SKUEL Architecture:
    - Uses CypherGenerator for graph queries
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    # DomainConfig consolidation (January 2026 Phase 3)
    # All configuration in one place, using centralized relationship registry
    # See: /docs/decisions/ADR-025-service-consolidation-patterns.md
    # Note: Principles use name instead of title, plus statement and why_important
    _config = create_activity_domain_config(
        dto_class=PrincipleDTO,
        model_class=Principle,
        domain_name="principles",
        date_field="created_at",
        completed_statuses=(),  # Principles don't have completion status
        search_fields=("name", "statement", "description", "why_important"),
    )

    # ========================================================================
    # DOMAIN SEARCH OPERATIONS PROTOCOL IMPLEMENTATION
    # ========================================================================
    # search() - inherited from BaseService using _dto_class, _model_class, _search_fields

    @with_error_handling("get_by_status", error_type="database")
    async def get_by_status(self, status: str, limit: int = 100) -> Result[list[Principle]]:
        """
        Filter principles by active/inactive status.

        Args:
            status: Status string ("active" or "inactive")
            limit: Maximum results to return

        Returns:
            Result containing principles with matching status
        """
        is_active = status.lower() in ("active", "true", "1")
        result = await self.backend.find_by(is_active=is_active, limit=limit)
        if result.is_error:
            return result

        principles = self._to_domain_models(result.value, PrincipleDTO, Principle)

        self.logger.debug(f"Found {len(principles)} principles with status '{status}'")
        return Result.ok(principles)

    @with_error_handling("get_by_domain", error_type="database")
    async def get_by_domain(self, domain: Domain, limit: int = 100) -> Result[list[Principle]]:
        """
        Filter principles by category (mapped from Domain concept).

        Note: Principles use PrincipleCategory, not Domain enum.
        This method maps Domain to the closest PrincipleCategory.

        Args:
            domain: Domain enum value
            limit: Maximum results to return

        Returns:
            Result containing principles in mapped category
        """
        from core.services.protocols import get_enum_value

        # Map Domain to PrincipleCategory
        domain_value = get_enum_value(domain)
        category_mapping = {
            "tech": PrincipleCategory.INTELLECTUAL.value,
            "health": PrincipleCategory.HEALTH.value,
            "personal": PrincipleCategory.PERSONAL.value,
            "professional": PrincipleCategory.PROFESSIONAL.value,
            "spiritual": PrincipleCategory.SPIRITUAL.value,
            "creative": PrincipleCategory.CREATIVE.value,
            "social": PrincipleCategory.RELATIONAL.value,
        }

        category_value = category_mapping.get(
            domain_value.lower(), PrincipleCategory.PERSONAL.value
        )

        result = await self.backend.find_by(category=category_value, limit=limit)
        if result.is_error:
            return result

        principles = self._to_domain_models(result.value, PrincipleDTO, Principle)

        self.logger.debug(
            f"Found {len(principles)} principles in domain '{domain_value}' (category: {category_value})"
        )
        return Result.ok(principles)

    @with_error_handling("get_prioritized", error_type="database")
    async def get_prioritized(
        self, user_context: UserContext, limit: int = 10
    ) -> Result[list[Principle]]:
        """
        Get principles prioritized for the user's current context.

        Uses UserContext to determine relevance:
        - Principle strength (core > strong > moderate)
        - Active goals alignment
        - Current focus areas
        - Review needs

        Args:
            user_context: User's current context (~240 fields)
            limit: Maximum results to return

        Returns:
            Result containing principles sorted by priority/relevance
        """
        # Get user's active principles
        result = await self.backend.find_by(user_uid=user_context.user_uid, is_active=True)
        if result.is_error:
            return result

        principles = self._to_domain_models(result.value, PrincipleDTO, Principle)

        # Score and sort by priority factors
        scored_principles = []
        for principle in principles:
            score = self._calculate_priority_score(principle, user_context)
            scored_principles.append((principle, score))

        # Sort by score descending
        from core.utils.sort_functions import get_second_item

        scored_principles.sort(key=get_second_item, reverse=True)

        # Return top N
        prioritized = [principle for principle, _ in scored_principles[:limit]]

        self.logger.info(
            f"Prioritized {len(prioritized)} principles for user {user_context.user_uid}"
        )
        return Result.ok(prioritized)

    def _calculate_priority_score(self, principle: Principle, user_context: UserContext) -> float:
        """
        Calculate priority score for a principle based on user context.

        Factors:
        - Strength level (core principles prioritized)
        - Alignment with active goals
        - Review needs
        - Integration level (guiding goals and habits)
        """
        score = 0.0

        # Strength level (0-40 points)
        strength_scores = {
            PrincipleStrength.CORE: 40,
            PrincipleStrength.STRONG: 30,
            PrincipleStrength.MODERATE: 20,
            PrincipleStrength.DEVELOPING: 15,
            PrincipleStrength.EXPLORING: 10,
        }
        score += strength_scores.get(principle.strength, 20)

        # Needs review (0-25 points)
        if principle.needs_review():
            score += 25

        # Well-aligned (0-20 points) - prioritize principles being lived
        if principle.is_well_aligned():
            score += 20
        elif principle.has_alignment_issues():
            score += 15  # Also prioritize those needing attention

        # Has concrete behaviors (0-15 points) - actionable principles
        if principle.has_concrete_behaviors():
            score += 15
        if principle.is_actionable():
            score += 10

        return score

    # get_by_relationship() - inherited from BaseService using _dto_class, _model_class

    async def get_due_soon(
        self,
        days_ahead: int = 30,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[list[Principle]]:
        """
        Get principles needing review within specified number of days.

        Principles "due" means they need alignment review based on
        last_review_date and a configurable review threshold.

        Args:
            days_ahead: Number of days to look ahead (default 30)
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing principles needing review soon
        """
        # Default review threshold is 90 days
        review_threshold_days = 90
        review_cutoff = date.today() - timedelta(days=review_threshold_days - days_ahead)

        # Build query with optional user filter
        user_clause = "AND p.user_uid = $user_uid" if user_uid else ""
        cypher_query = f"""
        MATCH (p:Principle)
        WHERE p.is_active = true
          AND (p.last_review_date IS NULL
               OR date(p.last_review_date) <= date($cutoff_date))
          {user_clause}
        RETURN p
        ORDER BY p.last_review_date ASC
        LIMIT $limit
        """

        params: dict[str, str | int] = {"cutoff_date": review_cutoff.isoformat(), "limit": limit}
        if user_uid:
            params["user_uid"] = user_uid

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Principles
        principles = []
        for record in result.value:
            principle_node = record["p"]
            dto = PrincipleDTO.from_dict(dict(principle_node))
            principles.append(Principle.from_dto(dto))

        self.logger.debug(
            f"Found {len(principles)} principles needing review within {days_ahead} days"
        )
        return Result.ok(principles)

    @with_error_handling("get_overdue", error_type="database")
    async def get_overdue(
        self,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[list[Principle]]:
        """
        Get principles past their review date (default 90-day threshold).

        Args:
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing overdue principles, sorted by how overdue
        """
        # Default review threshold is 90 days
        review_threshold_days = 90
        review_cutoff = date.today() - timedelta(days=review_threshold_days)

        # Build query with optional user filter
        user_clause = "AND p.user_uid = $user_uid" if user_uid else ""
        cypher_query = f"""
        MATCH (p:Principle)
        WHERE p.is_active = true
          AND (p.last_review_date IS NULL
               OR date(p.last_review_date) < date($cutoff_date))
          {user_clause}
        RETURN p
        ORDER BY p.last_review_date ASC
        LIMIT $limit
        """

        params: dict[str, str | int] = {"cutoff_date": review_cutoff.isoformat(), "limit": limit}
        if user_uid:
            params["user_uid"] = user_uid

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Principles
        principles = []
        for record in result.value:
            principle_node = record["p"]
            dto = PrincipleDTO.from_dict(dict(principle_node))
            principles.append(Principle.from_dto(dto))

        self.logger.debug(f"Found {len(principles)} overdue principles")
        return Result.ok(principles)

    # ========================================================================
    # PRINCIPLE-SPECIFIC SEARCH METHODS
    # ========================================================================

    @with_error_handling("get_by_strength", error_type="database")
    async def get_by_strength(
        self, strength: PrincipleStrength, limit: int = 100
    ) -> Result[list[Principle]]:
        """
        Get principles filtered by strength level.

        Args:
            strength: PrincipleStrength enum (CORE, STRONG, MODERATE, DEVELOPING, EXPLORING)
            limit: Maximum results to return

        Returns:
            Result containing principles with matching strength
        """
        from core.services.protocols import get_enum_value

        strength_value = get_enum_value(strength)
        result = await self.backend.find_by(strength=strength_value, limit=limit)
        if result.is_error:
            return result

        principles = self._to_domain_models(result.value, PrincipleDTO, Principle)

        self.logger.debug(f"Found {len(principles)} {strength_value} principles")
        return Result.ok(principles)

    @with_error_handling("get_by_category", error_type="database")
    async def get_by_category(
        self, category: PrincipleCategory | str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list[Principle]]:
        """
        Get principles in a specific category.

        Args:
            category: PrincipleCategory enum or string value
            limit: Maximum number of principles to return

        Returns:
            Result containing list of Principles
        """
        from core.services.protocols import get_enum_value

        category_value = get_enum_value(category) if not isinstance(category, str) else category
        result = await self.backend.find_by(category=category_value, limit=limit)
        if result.is_error:
            return result

        principles = self._to_domain_models(result.value, PrincipleDTO, Principle)

        self.logger.debug(f"Found {len(principles)} principles in category '{category_value}'")
        return Result.ok(principles)

    @with_error_handling("get_guiding_goals", error_type="database")
    async def get_guiding_goals(self, principle_uid: str) -> Result[list[str]]:
        """
        Get goal UIDs that a principle guides.

        Query: (Principle)-[:GUIDES_GOAL]->(Goal)

        Args:
            principle_uid: Principle UID

        Returns:
            Result containing goal UIDs guided by this principle
        """
        from core.models.relationship_names import RelationshipName

        result = await self.backend.get_related_uids(
            uid=principle_uid,
            relationship_type=RelationshipName.GUIDES_GOAL,
            direction="outgoing",
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        self.logger.debug(f"Found {len(result.value)} goals guided by principle {principle_uid}")
        return result

    @with_error_handling("get_inspiring_habits", error_type="database")
    async def get_inspiring_habits(self, principle_uid: str) -> Result[list[str]]:
        """
        Get habit UIDs that a principle inspires.

        Query: (Principle)-[:INSPIRES_HABIT]->(Habit)

        Args:
            principle_uid: Principle UID

        Returns:
            Result containing habit UIDs inspired by this principle
        """
        from core.models.relationship_names import RelationshipName

        result = await self.backend.get_related_uids(
            uid=principle_uid,
            relationship_type=RelationshipName.INSPIRES_HABIT,
            direction="outgoing",
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        self.logger.debug(f"Found {len(result.value)} habits inspired by principle {principle_uid}")
        return result

    @with_error_handling("get_for_choice", error_type="database")
    async def get_for_choice(self, choice_uid: str, limit: int = 10) -> Result[list[Principle]]:
        """
        Get principles relevant to a choice/decision.

        Query: (Principle)-[:GUIDES_CHOICE]->(Choice)

        Args:
            choice_uid: Choice UID
            limit: Maximum results to return

        Returns:
            Result containing principles that can guide this choice
        """
        return await self.get_by_relationship(
            related_uid=choice_uid,
            relationship_type=RelationshipName.GUIDES_CHOICE,
            direction="incoming",
        )

    @with_error_handling("get_for_goal", error_type="database")
    async def get_for_goal(self, goal_uid: str, limit: int = 10) -> Result[list[Principle]]:
        """
        Get principles that guide a specific goal.

        Query: (Principle)-[:GUIDES_GOAL]->(Goal)

        Args:
            goal_uid: Goal UID
            limit: Maximum results to return

        Returns:
            Result containing principles guiding this goal
        """
        return await self.get_by_relationship(
            related_uid=goal_uid,
            relationship_type=RelationshipName.GUIDES_GOAL,
            direction="incoming",
        )

    @with_error_handling("get_active_principles", error_type="database")
    async def get_active_principles(
        self, user_uid: str, limit: int = 100
    ) -> Result[list[Principle]]:
        """
        Get all active principles for a user.

        Args:
            user_uid: User UID
            limit: Maximum results to return

        Returns:
            Result containing active principles sorted by strength
        """
        result = await self.backend.find_by(user_uid=user_uid, is_active=True, limit=limit)
        if result.is_error:
            return result

        principles = self._to_domain_models(result.value, PrincipleDTO, Principle)

        # Sort by strength (core first)
        from core.utils.sort_functions import get_principle_strength_order

        principles.sort(key=get_principle_strength_order)

        self.logger.debug(f"Found {len(principles)} active principles for user {user_uid}")
        return Result.ok(principles)

    @with_error_handling("list_categories", error_type="database")
    async def list_categories(self) -> Result[list[str]]:
        """
        List all PrincipleCategory values.

        Returns:
            Result containing list of category strings
        """
        # Return all PrincipleCategory enum values
        categories = [c.value for c in PrincipleCategory]

        self.logger.debug(f"Returning {len(categories)} principle categories")
        return Result.ok(categories)

    @with_error_handling("get_needing_review", error_type="database")
    async def get_needing_review(
        self, days_threshold: int = 90, limit: int = 20
    ) -> Result[list[Principle]]:
        """
        Get principles that need alignment review.

        Args:
            days_threshold: Days since last review to trigger need (default 90)
            limit: Maximum results to return

        Returns:
            Result containing principles needing review
        """
        review_cutoff = date.today() - timedelta(days=days_threshold)

        cypher_query = """
        MATCH (p:Principle)
        WHERE p.is_active = true
          AND (p.last_review_date IS NULL
               OR date(p.last_review_date) < date($cutoff_date))
        RETURN p
        ORDER BY
            CASE WHEN p.last_review_date IS NULL THEN 0 ELSE 1 END,
            p.last_review_date ASC
        LIMIT $limit
        """

        result = await self.backend.execute_query(
            cypher_query,
            {"cutoff_date": review_cutoff.isoformat(), "limit": limit},
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Principles
        principles = []
        for record in result.value:
            principle_node = record["p"]
            dto = PrincipleDTO.from_dict(dict(principle_node))
            principles.append(Principle.from_dto(dto))

        self.logger.debug(
            f"Found {len(principles)} principles needing review (threshold: {days_threshold} days)"
        )
        return Result.ok(principles)

    @with_error_handling("get_related_principles", error_type="database")
    async def get_related_principles(
        self, principle_uid: str, depth: int = 2, limit: int = 10
    ) -> Result[list[Principle]]:
        """
        Get principles related to a given principle.

        Finds principles connected via RELATED_TO relationship (up to specified depth)
        or sharing similar categories/traditions.

        Args:
            principle_uid: Principle UID to find related principles for
            depth: Maximum relationship traversal depth (default 2)
            limit: Maximum results to return

        Returns:
            Result containing related principles
        """
        # Clamp depth to reasonable bounds
        depth = max(1, min(depth, 5))

        # First try RELATED_TO relationships up to specified depth
        # Use variable-length path traversal for deeper connections
        related_query = (
            """
        MATCH (source:Principle {uid: $uid})
        OPTIONAL MATCH (source)-[:RELATED_TO*1.."""
            + str(depth)
            + """]-(related:Principle)
        WHERE related.is_active = true AND related.uid <> $uid
        WITH DISTINCT related
        WHERE related IS NOT NULL
        RETURN related
        ORDER BY related.strength DESC
        LIMIT $limit
        """
        )

        result = await self.backend.execute_query(
            related_query,
            {"uid": principle_uid, "limit": limit},
        )

        if result.is_ok and result.value:
            principles = []
            for record in result.value:
                if record.get("related"):
                    dto = PrincipleDTO.from_dict(dict(record["related"]))
                    principles.append(Principle.from_dto(dto))
            if principles:
                self.logger.debug(
                    f"Found {len(principles)} principles related to {principle_uid} (depth={depth})"
                )
                return Result.ok(principles)

        # Fallback: find principles with same category
        principle_result = await self.backend.get(principle_uid)
        if principle_result.is_error:
            return Result.fail(principle_result.expect_error())

        if not principle_result.value:
            return Result.ok([])

        principle = self._to_domain_model(principle_result.value, PrincipleDTO, Principle)

        # Get principles in same category (excluding self)
        cypher_query = """
        MATCH (p:Principle)
        WHERE p.category = $category
          AND p.uid <> $uid
          AND p.is_active = true
        RETURN p
        ORDER BY p.strength DESC
        LIMIT $limit
        """

        from core.services.protocols import get_enum_value

        category_value = get_enum_value(principle.category)

        result = await self.backend.execute_query(
            cypher_query,
            {"category": category_value, "uid": principle_uid, "limit": limit},
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Principles
        principles = []
        for record in result.value:
            principle_node = record["p"]
            dto = PrincipleDTO.from_dict(dict(principle_node))
            principles.append(Principle.from_dto(dto))

        self.logger.debug(f"Found {len(principles)} principles related to {principle_uid}")
        return Result.ok(principles)

    # ========================================================================
    # GRAPH-AWARE FACETED SEARCH
    # ========================================================================
    # graph_aware_faceted_search() is inherited from BaseService (January 2026)
    # Configured via _graph_enrichment_patterns class attribute above
    # See: BaseService.graph_aware_faceted_search() for implementation

    # ========================================================================
    # INTELLIGENT SEARCH
    # ========================================================================

    @with_error_handling("intelligent_search", error_type="database")
    async def intelligent_search(
        self, query: str, user_uid: str | None = None, limit: int = 50
    ) -> Result[tuple[list[Principle], ParsedSearchQuery]]:
        """
        Natural language search with semantic filter extraction.

        Parses queries like "core health principles needing review" to extract:
        - Strength filters (core → CORE, strong → STRONG)
        - State filters (active, reviewing, dormant)
        - Category filters (health, personal, professional)
        - Domain filters (mapped from Domain enum)

        Args:
            query: Natural language search query
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing (principles, parsed_query) tuple

        Example:
            >>> result = await search.intelligent_search("core active principles")
            >>> principles, parsed = result.value
            >>> print(f"Filters: {parsed.to_filter_summary()}")
        """
        # Parse query for semantic filters
        parser = SearchQueryParser()
        parsed = parser.parse(query)
        query_lower = query.lower()

        # Build filters from parsed query
        filters: dict[str, object] = {}

        # Principle-specific: Strength extraction
        strength_keywords = {
            "core": PrincipleStrength.CORE,
            "strong": PrincipleStrength.STRONG,
            "moderate": PrincipleStrength.MODERATE,
            "developing": PrincipleStrength.DEVELOPING,
            "exploring": PrincipleStrength.EXPLORING,
            "new": PrincipleStrength.EXPLORING,
        }
        for keyword, strength in strength_keywords.items():
            if keyword in query_lower:
                filters["strength"] = strength.value
                break

        # Principle-specific: Category extraction
        category_keywords = {
            "health": PrincipleCategory.HEALTH,
            "personal": PrincipleCategory.PERSONAL,
            "professional": PrincipleCategory.PROFESSIONAL,
            "work": PrincipleCategory.PROFESSIONAL,
            "intellectual": PrincipleCategory.INTELLECTUAL,
            "spiritual": PrincipleCategory.SPIRITUAL,
            "relational": PrincipleCategory.RELATIONAL,
            "social": PrincipleCategory.RELATIONAL,
            "creative": PrincipleCategory.CREATIVE,
            "financial": PrincipleCategory.PROFESSIONAL,  # Financial maps to professional
        }
        for keyword, category in category_keywords.items():
            if keyword in query_lower:
                filters["category"] = category.value
                break

        # Principle-specific: State extraction (is_active)
        if "active" in query_lower:
            filters["is_active"] = True
        elif "inactive" in query_lower or "dormant" in query_lower:
            filters["is_active"] = False

        # Apply domain filter from parsed query (map to category if applicable)
        if parsed.domains and "category" not in filters:
            from core.services.protocols import get_enum_value

            domain_value = get_enum_value(parsed.domains[0])
            domain_to_category = {
                "tech": PrincipleCategory.INTELLECTUAL.value,
                "health": PrincipleCategory.HEALTH.value,
                "personal": PrincipleCategory.PERSONAL.value,
                "professional": PrincipleCategory.PROFESSIONAL.value,
                "spiritual": PrincipleCategory.SPIRITUAL.value,
                "creative": PrincipleCategory.CREATIVE.value,
                "social": PrincipleCategory.RELATIONAL.value,
            }
            if domain_value.lower() in domain_to_category:
                filters["category"] = domain_to_category[domain_value.lower()]

        # Execute search
        if filters:
            # Use filtered search via backend
            result = await self.backend.find_by(limit=limit, **filters)
            if result.is_error:
                return Result.fail(result.expect_error())
            principles = self._to_domain_models(result.value, PrincipleDTO, Principle)
        else:
            # Fall back to text search using cleaned query
            result = await self.search(parsed.text_query, limit=limit)
            if result.is_error:
                return Result.fail(result.expect_error())
            principles = result.value

        # Filter by user ownership if provided
        if user_uid and principles:
            principles = [p for p in principles if getattr(p, "user_uid", None) == user_uid]

        # Principle-specific: Review state filtering (post-filter)
        if "review" in query_lower or "reviewing" in query_lower:
            principles = [p for p in principles if p.needs_review()]
        elif "well-aligned" in query_lower or "aligned" in query_lower:
            principles = [p for p in principles if p.is_well_aligned()]

        self.logger.info(
            "Intelligent search: query=%r filters=%s results=%d",
            query,
            parsed.to_filter_summary(),
            len(principles),
        )

        return Result.ok((principles, parsed))
