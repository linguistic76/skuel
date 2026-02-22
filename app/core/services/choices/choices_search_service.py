"""
Choice Search Service - Search and Discovery Operations
========================================================

Handles search and discovery operations for choices/decisions.
Implements DomainSearchOperations[Ku] protocol plus choice-specific methods.

**Responsibilities:**
- Text search on title/description
- Filter by status, domain, urgency
- Time-based queries (pending, needing decision)
- Context-aware prioritization
- Graph-based relationship queries
- Principle alignment discovery

**Pattern:**
This service follows the SearchService pattern documented in:
/docs/patterns/search_service_pattern.md
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ports import BackendOperations

from core.models.enums import Priority
from core.models.enums.ku_enums import EntityStatus
from core.models.ku.choice import Choice
from core.models.ku.entity import Entity
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.relationship_names import RelationshipName
from core.models.search.query_parser import ParsedSearchQuery, SearchQueryParser
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_result_score


class ChoicesSearchService(BaseService["BackendOperations[Ku]", Ku]):
    """
    Choice search and discovery operations.

    Implements DomainSearchOperations[Ku] protocol for consistent
    search interface across all activity domains.

    Universal Methods (DomainSearchOperations protocol):
    - search() - Text search on title/description (inherited from BaseService)
    - get_by_status() - Filter by EntityStatus
    - get_by_domain() - Filter by Domain enum
    - get_prioritized() - Context-aware prioritization
    - get_by_relationship() - Graph relationship queries
    - get_due_soon() - Choices with upcoming deadlines
    - get_overdue() - Choices past deadline

    Choice-Specific Methods:
    - get_pending() - Pending/undecided choices
    - get_by_urgency() - Filter by urgency level
    - get_affecting_goal() - Choices affecting a goal
    - get_needing_decision() - Choices needing decision within N days
    - get_aligned_with_principle() - Choices aligned with a principle
    - get_by_category() - Filter by category

    Semantic Types Used:
    - AFFECTS_GOAL: Choice affects goal progress/direction
    - ALIGNED_WITH_PRINCIPLE: Choice aligned with guiding principle
    - REQUIRES_KNOWLEDGE: Choice requires knowledge for informed decision
    - IMPACTS_HABIT: Choice impacts habit formation/maintenance

    Source Tag: "choices_search_explicit"
    - Format: "choices_search_explicit" for user-defined relationships
    - Format: "choices_search_inferred" for system-discovered relationships

    Confidence Scoring:
    - 0.9+: User explicitly linked choice to goal/principle
    - 0.7-0.9: Inferred from domain/urgency alignment
    - <0.7: Suggested based on impact/context analysis

    SKUEL Architecture:
    - Uses CypherGenerator for graph queries
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    # DomainConfig consolidation (January 2026 Phase 3)
    # All configuration in one place, using centralized relationship registry
    # See: /docs/decisions/ADR-025-service-consolidation-patterns.md
    _config = create_activity_domain_config(
        dto_class=KuDTO,
        model_class=Entity,
        domain_name="choices",
        date_field="decision_deadline",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )

    def __init__(self, backend: BackendOperations[Ku]) -> None:
        """Initialize service with required backend."""
        super().__init__(backend=backend, service_name="choices.search")

    # Inherited from BaseService (December 2025):
    # - search(), get_by_status(), get_by_domain(), get_by_category(),
    # - list_categories(), get_by_relationship()

    # ========================================================================
    # DOMAIN SEARCH OPERATIONS PROTOCOL IMPLEMENTATION
    # ========================================================================
    # Inherited from BaseService: search(), get_by_status(), get_by_domain(),
    # get_by_category(), list_categories(), get_by_relationship()

    @with_error_handling("get_prioritized", error_type="database")
    async def get_prioritized(self, user_context: UserContext, limit: int = 10) -> Result[list[Ku]]:
        """
        Get choices prioritized for the user's current context.

        Uses UserContext to determine relevance:
        - Deadline proximity
        - Goal alignment
        - Urgency level
        - Impact potential

        Args:
            user_context: User's current context (~240 fields)
            limit: Maximum results to return

        Returns:
            Result containing choices sorted by priority/relevance
        """
        # Get user's pending choices
        result = await self.backend.find_by(user_uid=user_context.user_uid)
        if result.is_error:
            return result

        all_choices = self._to_domain_models(result.value, KuDTO, Entity)

        # Filter to pending/active choices
        pending_choices = [
            c
            for c in all_choices
            if not c.status
            or c.status.value
            not in {
                EntityStatus.COMPLETED.value,
                EntityStatus.CANCELLED.value,
                EntityStatus.ARCHIVED.value,
            }
        ]

        # Score and sort by priority factors
        scored_choices = []
        for choice in pending_choices:
            if not isinstance(choice, Choice):
                continue
            score = self._calculate_priority_score(choice, user_context)
            scored_choices.append((choice, score))

        # Sort by score descending
        scored_choices.sort(key=get_result_score, reverse=True)

        # Return top N
        prioritized = [choice for choice, _ in scored_choices[:limit]]

        self.logger.info(f"Prioritized {len(prioritized)} choices for user {user_context.user_uid}")
        return Result.ok(prioritized)

    def _calculate_priority_score(self, choice: Choice, user_context: UserContext) -> float:
        """
        Calculate priority score for a choice based on user context.

        Factors:
        - Deadline proximity (higher if deadline soon)
        - Priority level (using existing priority field)
        - Decision complexity (as proxy for impact)
        """
        score = 0.0
        today = date.today()

        # Deadline proximity (0-40 points) - use decision_deadline field
        if choice.decision_deadline:
            deadline_date = (
                choice.decision_deadline.date()
                if isinstance(choice.decision_deadline, datetime)
                else choice.decision_deadline
            )
            days_until = (deadline_date - today).days
            if days_until <= 0:
                score += 40  # Overdue
            elif days_until <= 3:
                score += 35  # Very urgent
            elif days_until <= 7:
                score += 30
            elif days_until <= 14:
                score += 20
            else:
                score += 10

        # Priority level (0-25 points) - use existing priority field
        from core.ports import get_enum_value

        priority_value = get_enum_value(choice.priority)
        if priority_value == "critical":
            score += 25
        elif priority_value == "high":
            score += 20
        elif priority_value == "medium":
            score += 15
        else:
            score += 5

        # High stakes bonus (0-20 points) - choices affecting multiple stakeholders or complex
        if choice.has_high_stakes():
            score += 20

        # Decision complexity as impact proxy (0-15 points)
        complexity = choice.calculate_decision_complexity()
        score += complexity * 15

        return score

    # get_by_relationship() - inherited from BaseService using _dto_class, _model_class

    @with_error_handling("get_due_soon", error_type="database")
    async def get_due_soon(
        self,
        days_ahead: int = 7,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[list[Ku]]:
        """
        Get choices with deadlines within specified number of days.

        Args:
            days_ahead: Number of days to look ahead (default 7)
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing choices due soon, sorted by deadline
        """
        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        # Build query with optional user filter
        user_clause = "AND c.user_uid = $user_uid" if user_uid else ""
        cypher_query = f"""
        MATCH (c:Ku {{ku_type: 'choice'}})
        WHERE c.deadline >= date($today)
          AND c.deadline <= date($end_date)
          AND c.status NOT IN ['completed', 'decided', 'cancelled', 'archived']
          {user_clause}
        RETURN c
        ORDER BY c.deadline ASC
        LIMIT $limit
        """

        params: dict[str, str | int] = {
            "today": today.isoformat(),
            "end_date": end_date.isoformat(),
            "limit": limit,
        }
        if user_uid:
            params["user_uid"] = user_uid

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Ku (choice type)
        choices = []
        for record in result.value:
            choice_node = record["c"]
            dto = KuDTO.from_dict(dict(choice_node))
            choices.append(Choice.from_dto(dto))

        self.logger.debug(f"Found {len(choices)} choices due within {days_ahead} days")
        return Result.ok(choices)

    @with_error_handling("get_overdue", error_type="database")
    async def get_overdue(
        self,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[list[Ku]]:
        """
        Get choices past their deadline and not decided.

        Args:
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing overdue choices
        """
        today = date.today()

        # Build query with optional user filter
        user_clause = "AND c.user_uid = $user_uid" if user_uid else ""
        cypher_query = f"""
        MATCH (c:Ku {{ku_type: 'choice'}})
        WHERE c.deadline < date($today)
          AND c.status NOT IN ['completed', 'decided', 'cancelled', 'archived']
          {user_clause}
        RETURN c
        ORDER BY c.deadline ASC
        LIMIT $limit
        """

        params: dict[str, str | int] = {"today": today.isoformat(), "limit": limit}
        if user_uid:
            params["user_uid"] = user_uid

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Ku (choice type)
        choices = []
        for record in result.value:
            choice_node = record["c"]
            dto = KuDTO.from_dict(dict(choice_node))
            choices.append(Choice.from_dto(dto))

        self.logger.debug(f"Found {len(choices)} overdue choices")
        return Result.ok(choices)

    # ========================================================================
    # CHOICE-SPECIFIC SEARCH METHODS
    # ========================================================================

    @with_error_handling("get_pending", error_type="database", uid_param="user_uid")
    async def get_pending(self, user_uid: str, limit: int = 100) -> Result[list[Ku]]:
        """
        Get pending/undecided choices for a user.

        Args:
            user_uid: User identifier
            limit: Maximum results

        Returns:
            Result containing pending choices
        """
        # Query for pending choices
        cypher_query = """
        MATCH (c:Ku {ku_type: 'choice'})
        WHERE c.user_uid = $user_uid
          AND c.status IN ['draft', 'active', 'scheduled']
        RETURN c
        ORDER BY c.deadline ASC, c.created_at DESC
        LIMIT $limit
        """

        result = await self.backend.execute_query(
            cypher_query, {"user_uid": user_uid, "limit": limit}
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Ku (choice type)
        choices = []
        for record in result.value:
            choice_node = record["c"]
            dto = KuDTO.from_dict(dict(choice_node))
            choices.append(Choice.from_dto(dto))

        self.logger.debug(f"Found {len(choices)} pending choices for user {user_uid}")
        return Result.ok(choices)

    @with_error_handling("get_by_urgency", error_type="database")
    async def get_by_urgency(
        self, urgency: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list[Ku]]:
        """
        Get choices by urgency level.

        Args:
            urgency: Urgency string (e.g., "critical", "high", "medium", "low")
            user_uid: Optional user filter
            limit: Maximum results

        Returns:
            Result containing choices with matching urgency
        """
        if user_uid:
            result = await self.backend.find_by(urgency=urgency, user_uid=user_uid, limit=limit)
        else:
            result = await self.backend.find_by(urgency=urgency, limit=limit)

        if result.is_error:
            return result

        choices = self._to_domain_models(result.value, KuDTO, Entity)

        self.logger.debug(f"Found {len(choices)} choices with urgency '{urgency}'")
        return Result.ok(choices)

    @with_error_handling("get_affecting_goal", error_type="database", uid_param="goal_uid")
    async def get_affecting_goal(self, goal_uid: str) -> Result[list[Ku]]:
        """
        Get choices that affect a specific goal.

        Query: (Choice)-[:AFFECTS_GOAL]->(Goal)

        Args:
            goal_uid: Goal UID

        Returns:
            Result containing choices affecting the goal
        """
        return await self.get_by_relationship(
            related_uid=goal_uid,
            relationship_type=RelationshipName.AFFECTS_GOAL,
            direction="incoming",
        )

    @with_error_handling("get_needing_decision", error_type="database", uid_param="user_uid")
    async def get_needing_decision(self, user_uid: str, deadline_days: int = 7) -> Result[list[Ku]]:
        """
        Get choices that need a decision within N days.

        Choices needing decision:
        - Have a deadline within deadline_days
        - Status is pending/active
        - Not yet decided

        Args:
            user_uid: User identifier
            deadline_days: Days to look ahead

        Returns:
            Result containing choices needing decision
        """
        today = date.today()
        end_date = today + timedelta(days=deadline_days)

        # Query for choices needing decision
        cypher_query = """
        MATCH (c:Ku {ku_type: 'choice'})
        WHERE c.user_uid = $user_uid
          AND c.deadline <= date($end_date)
          AND c.status NOT IN ['completed', 'decided', 'cancelled', 'archived']
        RETURN c
        ORDER BY c.deadline ASC
        """

        result = await self.backend.execute_query(
            cypher_query, {"user_uid": user_uid, "end_date": end_date.isoformat()}
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Ku (choice type)
        choices = []
        for record in result.value:
            choice_node = record["c"]
            dto = KuDTO.from_dict(dict(choice_node))
            choices.append(Choice.from_dto(dto))

        self.logger.debug(
            f"Found {len(choices)} choices needing decision within {deadline_days} days"
        )
        return Result.ok(choices)

    @with_error_handling(
        "get_aligned_with_principle", error_type="database", uid_param="principle_uid"
    )
    async def get_aligned_with_principle(
        self, principle_uid: str, min_confidence: float = 0.7
    ) -> Result[list[Ku]]:
        """
        Get choices aligned with a specific principle.

        Query: (Ku {ku_type: 'choice'})-[:ALIGNED_WITH_PRINCIPLE]->(Ku {ku_type: 'principle'})

        Args:
            principle_uid: Principle UID
            min_confidence: Minimum alignment confidence

        Returns:
            Result containing aligned choices
        """
        # Query for choices aligned with principle
        cypher_query = """
        MATCH (c:Ku {ku_type: 'choice'})-[r:ALIGNED_WITH_PRINCIPLE]->(p:Ku {uid: $principle_uid, ku_type: 'principle'})
        WHERE r.confidence >= $min_confidence
        RETURN c
        ORDER BY r.confidence DESC
        """

        result = await self.backend.execute_query(
            cypher_query,
            {"principle_uid": principle_uid, "min_confidence": min_confidence},
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Ku (choice type)
        choices = []
        for record in result.value:
            choice_node = record["c"]
            dto = KuDTO.from_dict(dict(choice_node))
            choices.append(Choice.from_dto(dto))

        self.logger.debug(f"Found {len(choices)} choices aligned with principle {principle_uid}")
        return Result.ok(choices)

    # get_by_category() and list_categories() - inherited from BaseService

    @with_error_handling("get_decided", error_type="database", uid_param="user_uid")
    async def get_decided(
        self, user_uid: str, days_back: int = 90, limit: int = 100
    ) -> Result[list[Ku]]:
        """
        Get decided/completed choices for a user.

        Args:
            user_uid: User identifier
            days_back: Number of days of history
            limit: Maximum results

        Returns:
            Result containing decided choices
        """
        lookback_date = date.today() - timedelta(days=days_back)

        # Query for decided choices
        cypher_query = """
        MATCH (c:Ku {ku_type: 'choice'})
        WHERE c.user_uid = $user_uid
          AND c.status IN ['active', 'completed']
          AND c.decided_at >= date($lookback_date)
        RETURN c
        ORDER BY c.decided_at DESC
        LIMIT $limit
        """

        result = await self.backend.execute_query(
            cypher_query,
            {
                "user_uid": user_uid,
                "lookback_date": lookback_date.isoformat(),
                "limit": limit,
            },
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Ku (choice type)
        choices = []
        for record in result.value:
            choice_node = record["c"]
            dto = KuDTO.from_dict(dict(choice_node))
            choices.append(Choice.from_dto(dto))

        self.logger.debug(f"Found {len(choices)} decided choices for user {user_uid}")
        return Result.ok(choices)

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
    ) -> Result[tuple[list[Ku], ParsedSearchQuery]]:
        """
        Natural language search with semantic filter extraction.

        Parses queries like "urgent pending health choices" to extract:
        - Urgency filters (urgent -> high priority, soon -> medium)
        - Decision state filters (pending, decided, deferred)
        - Status filters (active, completed, cancelled)
        - Domain filters (health, tech, etc.)

        Args:
            query: Natural language search query
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing (choices, parsed_query) tuple

        Example:
            >>> result = await search.intelligent_search("urgent pending choices")
            >>> choices, parsed = result.value
            >>> print(f"Filters: {parsed.to_filter_summary()}")
        """
        # Parse query for semantic filters
        parser = SearchQueryParser()
        parsed = parser.parse(query)
        query_lower = query.lower()

        # Build filters from parsed query
        filters: dict[str, object] = {}

        # Choice-specific: Urgency/priority extraction
        if "urgent" in query_lower or "now" in query_lower or "asap" in query_lower:
            filters["priority"] = Priority.CRITICAL.value
        elif "important" in query_lower or "high" in query_lower:
            filters["priority"] = Priority.HIGH.value
        elif "soon" in query_lower:
            filters["priority"] = Priority.MEDIUM.value
        elif "later" in query_lower or "low" in query_lower:
            filters["priority"] = Priority.LOW.value
        # Also check parsed priorities from SearchQueryParser
        elif parsed.priorities:
            highest_priority = parsed.get_highest_priority()
            if highest_priority:
                filters["priority"] = highest_priority.value

        # Choice-specific: Decision state extraction
        decision_state: str | None = None
        if "pending" in query_lower or "undecided" in query_lower:
            decision_state = "pending"
        elif "decided" in query_lower or "completed" in query_lower:
            decision_state = "decided"
        elif "deferred" in query_lower or "postponed" in query_lower:
            decision_state = "deferred"

        # Apply status filter from parsed query (use first status if multiple)
        if parsed.statuses:
            filters["status"] = parsed.statuses[0].value
        elif decision_state:
            # Map decision state to status
            # DRAFT = undecided choice, COMPLETED = decided, PAUSED = deferred
            state_to_status = {
                "pending": EntityStatus.DRAFT.value,
                "decided": EntityStatus.COMPLETED.value,
                "deferred": EntityStatus.PAUSED.value,
            }
            filters["status"] = state_to_status.get(decision_state, EntityStatus.DRAFT.value)

        # Apply domain filter from parsed query (use first domain if multiple)
        if parsed.domains:
            filters["domain"] = parsed.domains[0].value

        # Execute search
        if filters:
            # Use filtered search via backend
            result = await self.backend.find_by(limit=limit, **filters)
            if result.is_error:
                return Result.fail(result.expect_error())
            choices = self._to_domain_models(result.value, KuDTO, Entity)
        else:
            # Fall back to text search using cleaned query
            result = await self.search(parsed.text_query, limit=limit)
            if result.is_error:
                return Result.fail(result.expect_error())
            choices = result.value

        # Filter by user ownership if provided
        if user_uid and choices:
            choices = [c for c in choices if getattr(c, "user_uid", None) == user_uid]

        # Choice-specific: High stakes filtering (post-filter)
        if "high stakes" in query_lower or "important decision" in query_lower:
            choices = [c for c in choices if isinstance(c, Choice) and c.has_high_stakes()]

        self.logger.info(
            "Intelligent search: query=%r filters=%s results=%d",
            query,
            parsed.to_filter_summary(),
            len(choices),
        )

        return Result.ok((choices, parsed))
