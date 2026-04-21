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
"""

from datetime import date, timedelta
from typing import Any

from core.models.enums import Domain, EntityStatus
from core.models.enums.principle_enums import PrincipleCategory, PrincipleStrength
from core.models.principle.principle import Principle
from core.models.principle.principle_dto import PrincipleDTO
from core.models.relationship_names import RelationshipName
from core.models.search.query_parser import ParsedSearchQuery, SearchQueryParser
from core.models.search.scoring import score_principle
from core.models.type_hints import UserUID
from core.ports.domain_protocols import PrinciplesOperations
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_result_score


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
    - get_upcoming() - Principles needing review soon (approaching threshold)
    - get_overdue() - Principles past review date

    Principle-Specific Methods:
    - get_by_strength() - Filter by PrincipleStrength (core, strong, moderate, etc.)
    - get_by_category() - Filter by PrincipleCategory
    - get_guiding_goals() - Principles guiding specific goals
    - get_inspiring_habits() - Principles inspiring specific habits
    - get_for_choice() - Principles relevant to a decision
    - get_active() - Get all active principles for user (overrides base — uses is_active flag)
    - get_upcoming() - Principles approaching review threshold (overrides base)
    - get_overdue() - Principles past review threshold (delegates to get_needing_review)
    - get_needing_review() - Principles past review threshold

    Semantic Types Used:
    - GUIDES_GOAL: Principle provides guidance for goal setting/achievement
    - INSPIRES_HABIT: Principle inspires habit formation/maintenance
    - GUIDES_CHOICE: Principle guides decision-making
    - RELATED_TO: Principle relates to another principle
    """

    # DomainConfig consolidation (January 2026)
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
    async def get_by_status(
        self, status: EntityStatus | str, limit: int = 100, user_uid: UserUID | None = None
    ) -> Result[list[Principle]]:
        """
        Filter principles by active/inactive status.

        Args:
            status: EntityStatus enum or status string ("active" or "inactive")
            limit: Maximum results to return
            user_uid: Optional user UID to scope results to owner

        Returns:
            Result containing principles with matching status
        """
        status_str = status.value if isinstance(status, EntityStatus) else status
        is_active = status_str.lower() in ("active", "true", "1")
        filters: dict[str, Any] = {"is_active": is_active, "limit": limit}
        if user_uid:
            filters["user_uid"] = user_uid
        result = await self.backend.find_by(**filters)
        if result.is_error:
            return Result.fail(result)

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
        from core.ports import get_enum_value

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
            return Result.fail(result)

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
            return Result.fail(result)

        principles = [
            p
            for p in self._to_domain_models(result.value, PrincipleDTO, Principle)
            if isinstance(p, Principle)
        ]

        scored_principles = [
            (principle, score_principle(principle, user_context).total) for principle in principles
        ]
        scored_principles.sort(key=get_result_score, reverse=True)

        prioritized = [principle for principle, _ in scored_principles[:limit]]

        self.logger.info(
            f"Prioritized {len(prioritized)} principles for user {user_context.user_uid}"
        )
        return Result.ok(prioritized)

    # get_by_relationship() - inherited from BaseService using _dto_class, _model_class

    async def get_upcoming(
        self,
        days_ahead: int = 30,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list[Principle]]:
        """
        Get principles needing review within specified number of days.

        Override of TimeQueryMixin.get_upcoming — principles don't have a
        due_date field. "Upcoming" means the principle is approaching the
        90-day review threshold (last_review_date within days_ahead of cutoff).

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

        result = await self.backend.get_principles_due_for_review(
            cutoff_date=review_cutoff.isoformat(),
            user_uid=user_uid,
            limit=limit,
        )
        if result.is_error:
            return Result.fail(result)

        principles = self._to_domain_models(result.value, PrincipleDTO, Principle)

        self.logger.debug(
            f"Found {len(principles)} principles needing review within {days_ahead} days"
        )
        return Result.ok(principles)

    @with_error_handling("get_overdue", error_type="database")
    async def get_overdue(
        self,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list[Principle]]:
        """
        Get principles past their 90-day review threshold.

        Thin delegation to get_needing_review(days_threshold=90) — "overdue"
        and "needing review at the default threshold" are the same concept
        for principles.

        Args:
            user_uid: Optional user UID to filter by ownership (forwarded)
            limit: Maximum results to return

        Returns:
            Result containing overdue principles
        """
        return await self.get_needing_review(user_uid=user_uid, days_threshold=90, limit=limit)

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
        from core.ports import get_enum_value

        strength_value = get_enum_value(strength)
        result = await self.backend.find_by(strength=strength_value, limit=limit)
        if result.is_error:
            return Result.fail(result)

        principles = self._to_domain_models(result.value, PrincipleDTO, Principle)

        self.logger.debug(f"Found {len(principles)} {strength_value} principles")
        return Result.ok(principles)

    @with_error_handling("get_by_category", error_type="database")
    async def get_by_category(
        self, category: PrincipleCategory | str, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Principle]]:
        """
        Get principles in a specific category.

        Args:
            category: PrincipleCategory enum or string value
            limit: Maximum number of principles to return

        Returns:
            Result containing list of Principles
        """
        from core.ports import get_enum_value

        category_value = get_enum_value(category) if not isinstance(category, str) else category
        result = await self.backend.find_by(category=category_value, limit=limit)
        if result.is_error:
            return Result.fail(result)

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
        result = await self.backend.get_related_uids(
            uid=principle_uid,
            relationship_type=RelationshipName.GUIDES_GOAL,
            direction="outgoing",
        )
        if result.is_error:
            return Result.fail(result)

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
        result = await self.backend.get_related_uids(
            uid=principle_uid,
            relationship_type=RelationshipName.INSPIRES_HABIT,
            direction="outgoing",
        )
        if result.is_error:
            return Result.fail(result)

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

    @with_error_handling("get_for_habit", error_type="database")
    async def get_for_habit(self, habit_uid: str, limit: int = 10) -> Result[list[Principle]]:
        """
        Get principles aligned with a specific habit.

        Query: (Habit)-[:ALIGNED_WITH_PRINCIPLE]->(Principle)

        Args:
            habit_uid: Habit UID
            limit: Maximum results to return

        Returns:
            Result containing principles aligned with this habit
        """
        return await self.get_by_relationship(
            related_uid=habit_uid,
            relationship_type=RelationshipName.ALIGNED_WITH_PRINCIPLE,
            direction="outgoing",
        )

    @with_error_handling("get_active", error_type="database")
    async def get_active(self, user_uid: UserUID, limit: int = 100) -> Result[list[Principle]]:
        """
        Get all active principles for a user.

        Override of TimeQueryMixin.get_active — principles use an explicit
        is_active: bool flag rather than EntityStatus terminal states.

        Args:
            user_uid: User UID
            limit: Maximum results to return

        Returns:
            Result containing active principles sorted by strength
        """
        result = await self.backend.find_by(user_uid=user_uid, is_active=True, limit=limit)
        if result.is_error:
            return Result.fail(result)

        principles = self._to_domain_models(result.value, PrincipleDTO, Principle)

        # Sort by strength (core first)
        from core.utils.sort_functions import get_principle_strength_order

        principles.sort(key=get_principle_strength_order)

        self.logger.debug(f"Found {len(principles)} active principles for user {user_uid}")
        return Result.ok(principles)

    @with_error_handling("get_needing_review", error_type="database")
    async def get_needing_review(
        self,
        user_uid: UserUID | None = None,
        days_threshold: int = 90,
        limit: int = 20,
    ) -> Result[list[Principle]]:
        """
        Get principles that need alignment review.

        Args:
            user_uid: Optional user UID to filter by ownership
            days_threshold: Days since last review to trigger need (default 90)
            limit: Maximum results to return

        Returns:
            Result containing principles needing review
        """
        review_cutoff = date.today() - timedelta(days=days_threshold)

        result = await self.backend.get_principles_needing_review(
            cutoff_date=review_cutoff.isoformat(),
            user_uid=user_uid,
            limit=limit,
            prioritize_never_reviewed=True,
        )
        if result.is_error:
            return Result.fail(result)

        principles = self._to_domain_models(result.value, PrincipleDTO, Principle)

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
        # First try RELATED_TO relationships up to specified depth
        result = await self.backend.get_related_principles_by_traversal(
            uid=principle_uid, depth=depth, limit=limit
        )

        if result.is_ok and result.value:
            principles = self._to_domain_models(result.value, PrincipleDTO, Principle)
            if principles:
                self.logger.debug(
                    f"Found {len(principles)} principles related to {principle_uid} (depth={depth})"
                )
                return Result.ok(principles)

        # Fallback: find principles with same category
        principle_result = await self.backend.get(principle_uid)
        if principle_result.is_error:
            return Result.fail(principle_result)

        if not principle_result.value:
            return Result.ok([])

        principle = self._to_domain_model(principle_result.value, PrincipleDTO, Principle)
        assert isinstance(principle, Principle)

        from core.ports import get_enum_value

        category_value = get_enum_value(principle.category)

        result = await self.backend.get_principles_by_category(
            category=category_value, exclude_uid=principle_uid, limit=limit
        )
        if result.is_error:
            return Result.fail(result)

        principles = self._to_domain_models(result.value, PrincipleDTO, Principle)

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
        self, query: str, user_uid: UserUID | None = None, limit: int = 50
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
            from core.ports import get_enum_value

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
                return Result.fail(result)
            principles = self._to_domain_models(result.value, PrincipleDTO, Principle)
        else:
            # Fall back to text search using cleaned query
            result = await self.search(parsed.text_query, limit=limit)
            if result.is_error:
                return Result.fail(result)
            principles = result.value

        # Filter by user ownership if provided
        if user_uid and principles:
            principles = [p for p in principles if getattr(p, "user_uid", None) == user_uid]

        # Principle-specific: Review state filtering (post-filter)
        if "review" in query_lower or "reviewing" in query_lower:
            principles = [p for p in principles if isinstance(p, Principle) and p.needs_review()]
        elif "well-aligned" in query_lower or "aligned" in query_lower:
            principles = [p for p in principles if isinstance(p, Principle) and p.is_well_aligned()]

        self.logger.info(
            "Intelligent search: query=%r filters=%s results=%d",
            query,
            parsed.to_filter_summary(),
            len(principles),
        )

        return Result.ok((principles, parsed))
