"""
Goal Search Service - Search and Discovery Operations
======================================================

Handles search and discovery operations for goals.
Implements DomainSearchOperations[Goal] protocol plus goal-specific methods.

**Responsibilities:**
- Text search on title/description
- Filter by status, domain/category, timeframe
- Time-based queries (due soon, overdue)
- Context-aware prioritization
- Graph-based relationship queries

**Pattern:**
This service follows the SearchService pattern documented in:
/docs/patterns/search_service_pattern.md
"""

from datetime import date, timedelta

from core.models.enums import KuStatus
from core.models.enums.ku_enums import GoalTimeframe
from core.models.ku.ku_dto import KuDTO
from core.models.ku.ku_goal import GoalKu
from core.models.relationship_names import RelationshipName
from core.models.search.query_parser import ParsedSearchQuery, SearchQueryParser
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.ports.domain_protocols import GoalsOperations
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_result_score


class GoalsSearchService(BaseService[GoalsOperations, GoalKu]):
    """
    Goal search and discovery operations.

    Implements DomainSearchOperations[Goal] protocol for consistent
    search interface across all activity domains.

    Universal Methods (DomainSearchOperations protocol):
    - search() - Text search on title/description (inherited from BaseService)
    - get_by_status() - Filter by KuStatus
    - get_by_domain() - Filter by Domain enum
    - get_prioritized() - Context-aware prioritization
    - get_by_relationship() - Graph relationship queries
    - get_due_soon() - Goals due within N days
    - get_overdue() - Past-due goals

    Goal-Specific Methods:
    - get_by_timeframe() - Filter by GoalTimeframe (weekly, monthly, quarterly, yearly)
    - get_by_category() - Filter by domain/category string
    - get_needing_habits() - Goals that would benefit from supporting habits
    - get_blocked_by_knowledge() - Goals blocked by knowledge prerequisites
    - list_categories() - Get all unique goal categories

    Semantic Types Used:
    - FULFILLS_GOAL: Task contributes to goal completion
    - SUPPORTS_GOAL: Habit supports goal achievement
    - PARENT_GOAL: Goal is a sub-goal of another
    - REQUIRES_KNOWLEDGE: Goal requires knowledge prerequisites
    - SERVES_LIFE_PATH: Goal aligns with ultimate life path

    Source Tag: "goals_search_explicit"
    - Format: "goals_search_explicit" for user-defined relationships
    - Format: "goals_search_inferred" for system-discovered relationships

    Confidence Scoring:
    - 0.9+: User explicitly linked entities to goal
    - 0.7-0.9: Inferred from domain/timeframe alignment
    - <0.7: Suggested based on content/context similarity

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
        model_class=GoalKu,
        domain_name="goals",
        date_field="target_date",
        completed_statuses=(KuStatus.COMPLETED.value, KuStatus.CANCELLED.value),
        category_field="domain",  # Goals use 'domain' field for categorization
        entity_label="Ku",
    )

    # Inherited from BaseService (December 2025):
    # - search() - Text search on title/description
    # - get_by_relationship() - Graph relationship queries
    # - get_by_status() - Filter by status field
    # - get_by_domain() - Filter by domain field
    # - get_by_category() - Filter by domain field (via _category_field)
    # - list_categories() - List unique domain values

    # ========================================================================
    # DOMAIN SEARCH OPERATIONS PROTOCOL IMPLEMENTATION
    # ========================================================================
    # Inherited from BaseService: search(), get_by_status(), get_by_domain(),
    # get_by_category(), list_categories(), get_by_relationship()

    @with_error_handling("get_prioritized", error_type="database")
    async def get_prioritized(
        self, user_context: UserContext, limit: int = 10
    ) -> Result[list[GoalKu]]:
        """
        Get goals prioritized for the user's current context.

        Uses UserContext to determine relevance:
        - Current focus areas and active tasks
        - Learning position and knowledge gaps
        - Goal progress and momentum
        - Deadline proximity

        Args:
            user_context: User's current context (~240 fields)
            limit: Maximum results to return

        Returns:
            Result containing goals sorted by priority/relevance
        """
        # Get user's active goals
        result = await self.backend.find_by(
            user_uid=user_context.user_uid, status=KuStatus.ACTIVE.value
        )
        if result.is_error:
            return result

        goals = self._to_domain_models(result.value, KuDTO, GoalKu)

        # Score and sort by priority factors
        scored_goals = []
        for goal in goals:
            score = self._calculate_priority_score(goal, user_context)
            scored_goals.append((goal, score))

        # Sort by score descending
        scored_goals.sort(key=get_result_score, reverse=True)

        # Return top N
        prioritized = [goal for goal, _ in scored_goals[:limit]]

        self.logger.info(f"Prioritized {len(prioritized)} goals for user {user_context.user_uid}")
        return Result.ok(prioritized)

    def _calculate_priority_score(self, goal: GoalKu, user_context: UserContext) -> float:
        """
        Calculate priority score for a goal based on user context.

        Factors:
        - Deadline proximity (higher score if closer)
        - Progress momentum (higher if making progress)
        - Domain alignment with current focus
        - Has active tasks (execution context)
        """
        score = 0.0

        # Deadline proximity (0-40 points)
        if goal.target_date:
            days_until = (goal.target_date - date.today()).days
            if days_until <= 0:
                score += 40  # Overdue = highest priority
            elif days_until <= 7:
                score += 35
            elif days_until <= 30:
                score += 25
            elif days_until <= 90:
                score += 15
            else:
                score += 5

        # Progress momentum (0-30 points)
        progress = goal.progress_percentage or 0.0
        if 25 <= progress <= 75:
            score += 30  # In-progress goals get priority
        elif progress > 75:
            score += 25  # Near completion
        elif progress > 0:
            score += 15  # Started but slow
        else:
            score += 10  # Not started

        # Priority level (0-20 points)
        if goal.priority:
            from core.models.enums import Priority
            from core.ports import get_enum_value

            priority_value = get_enum_value(goal.priority)
            if priority_value == Priority.CRITICAL.value:
                score += 20
            elif priority_value == Priority.HIGH.value:
                score += 15
            elif priority_value == Priority.MEDIUM.value:
                score += 10
            else:
                score += 5

        # Context alignment (0-10 points)
        if user_context.active_goal_uids and goal.uid in user_context.active_goal_uids:
            score += 10  # Already in active focus

        return score

    # get_by_relationship() - inherited from BaseService using _dto_class, _model_class

    @with_error_handling("get_due_soon", error_type="database")
    async def get_due_soon(
        self,
        days_ahead: int = 7,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[list[GoalKu]]:
        """
        Get goals due within specified number of days.

        Args:
            days_ahead: Number of days to look ahead (default 7)
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing goals due soon, sorted by due date
        """
        end_date = date.today() + timedelta(days=days_ahead)

        # Build query with optional user filter
        user_clause = "AND g.user_uid = $user_uid" if user_uid else ""
        cypher_query = f"""
        MATCH (g:Ku {{ku_type: 'goal'}})
        WHERE g.target_date >= date($today)
          AND g.target_date <= date($end_date)
          AND g.status IN ['active', 'in_progress', 'on_track']
          {user_clause}
        RETURN g
        ORDER BY g.target_date ASC
        LIMIT $limit
        """

        params: dict[str, str | int] = {
            "today": date.today().isoformat(),
            "end_date": end_date.isoformat(),
            "limit": limit,
        }
        if user_uid:
            params["user_uid"] = user_uid

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Goals
        goals = []
        for record in result.value:
            goal_node = record["g"]
            dto = KuDTO.from_dict(dict(goal_node))
            goals.append(GoalKu.from_dto(dto))

        self.logger.debug(f"Found {len(goals)} goals due within {days_ahead} days")
        return Result.ok(goals)

    @with_error_handling("get_overdue", error_type="database")
    async def get_overdue(
        self,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[list[GoalKu]]:
        """
        Get goals past their target date and not completed.

        Args:
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing overdue goals, sorted by how overdue
        """
        # Build query with optional user filter
        user_clause = "AND g.user_uid = $user_uid" if user_uid else ""
        cypher_query = f"""
        MATCH (g:Ku {{ku_type: 'goal'}})
        WHERE g.target_date < date($today)
          AND g.status NOT IN ['completed', 'achieved', 'abandoned', 'archived', 'cancelled']
          {user_clause}
        RETURN g
        ORDER BY g.target_date ASC
        LIMIT $limit
        """

        params: dict[str, str | int] = {"today": date.today().isoformat(), "limit": limit}
        if user_uid:
            params["user_uid"] = user_uid

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Goals
        goals = []
        for record in result.value:
            goal_node = record["g"]
            dto = KuDTO.from_dict(dict(goal_node))
            goals.append(GoalKu.from_dto(dto))

        self.logger.debug(f"Found {len(goals)} overdue goals")
        return Result.ok(goals)

    # ========================================================================
    # GOAL-SPECIFIC SEARCH METHODS
    # ========================================================================

    @with_error_handling("get_by_timeframe", error_type="database")
    async def get_by_timeframe(
        self, timeframe: GoalTimeframe, limit: int = 100
    ) -> Result[list[GoalKu]]:
        """
        Get goals filtered by timeframe.

        Args:
            timeframe: GoalTimeframe enum (WEEKLY, MONTHLY, QUARTERLY, YEARLY, LIFE)
            limit: Maximum results to return

        Returns:
            Result containing goals with matching timeframe
        """
        from core.ports import get_enum_value

        timeframe_value = get_enum_value(timeframe)
        result = await self.backend.find_by(timeframe=timeframe_value, limit=limit)
        if result.is_error:
            return result

        goals = self._to_domain_models(result.value, KuDTO, GoalKu)

        self.logger.debug(f"Found {len(goals)} {timeframe_value} goals")
        return Result.ok(goals)

    # get_by_category() - inherited from BaseService (uses _category_field = "domain")

    @with_error_handling("get_needing_habits", error_type="database")
    async def get_needing_habits(
        self, user_context: UserContext, limit: int = 20
    ) -> Result[list[GoalKu]]:
        """
        Get goals that would benefit from supporting habits.

        A goal needs habits if:
        - It's active/in-progress
        - Has low or no supporting habits
        - Has been active for a while without good progress

        Args:
            user_context: User's current context
            limit: Maximum results to return

        Returns:
            Result containing goals needing habit support
        """
        # Get user's active goals
        result = await self.backend.find_by(
            user_uid=user_context.user_uid, status=KuStatus.ACTIVE.value
        )
        if result.is_error:
            return result

        all_goals = self._to_domain_models(result.value, KuDTO, GoalKu)

        # Check each goal for habit support
        goals_needing_habits = []
        for goal in all_goals:
            # Count supporting habits
            habit_count_result = await self.backend.count_related(
                uid=goal.uid,
                relationship_type=RelationshipName.SUPPORTS_GOAL,
                direction="incoming",
            )
            habit_count = habit_count_result.value if habit_count_result.is_ok else 0

            # Goals with 0-1 habits and low progress are candidates
            progress = goal.progress_percentage or 0.0
            if habit_count <= 1 and progress < 50:
                goals_needing_habits.append(goal)

        # Sort by progress (lowest first - most in need)
        def get_progress(goal: GoalKu) -> float:
            """Get progress percentage for sorting, defaulting to 0.0."""
            return goal.progress_percentage or 0.0

        goals_needing_habits.sort(key=get_progress)

        result_goals = goals_needing_habits[:limit]

        self.logger.info(
            f"Found {len(result_goals)} goals needing habit support for user {user_context.user_uid}"
        )
        return Result.ok(result_goals)

    @with_error_handling("get_blocked_by_knowledge", error_type="database")
    async def get_blocked_by_knowledge(
        self, user_context: UserContext, limit: int = 20
    ) -> Result[list[GoalKu]]:
        """
        Get goals blocked by missing knowledge prerequisites.

        A goal is blocked by knowledge if it has REQUIRES_KNOWLEDGE
        relationships to knowledge units the user hasn't mastered.

        Args:
            user_context: User's current context (includes knowledge_mastery)
            limit: Maximum results to return

        Returns:
            Result containing goals blocked by knowledge gaps
        """
        # Get user's active goals
        result = await self.backend.find_by(
            user_uid=user_context.user_uid, status=KuStatus.ACTIVE.value
        )
        if result.is_error:
            return result

        all_goals = self._to_domain_models(result.value, KuDTO, GoalKu)

        # Check each goal for knowledge prerequisites
        blocked_goals = []
        user_mastery = user_context.knowledge_mastery or {}

        for goal in all_goals:
            # Get required knowledge UIDs
            knowledge_uids_result = await self.backend.get_related_uids(
                uid=goal.uid,
                relationship_type=RelationshipName.REQUIRES_KNOWLEDGE,
                direction="outgoing",
            )
            if knowledge_uids_result.is_error:
                continue

            required_knowledge_uids = knowledge_uids_result.value

            # Check if user has mastered all required knowledge
            missing_knowledge = []
            for ku_uid in required_knowledge_uids:
                mastery = user_mastery.get(ku_uid, 0.0)
                if mastery < 0.7:  # Threshold for "mastered"
                    missing_knowledge.append(ku_uid)

            if missing_knowledge:
                # Store missing knowledge in goal metadata for UI display
                goal.metadata["blocked_by_knowledge"] = missing_knowledge
                blocked_goals.append(goal)

        # Sort by number of missing prerequisites (fewest first - easiest to unblock)
        def get_blocked_knowledge_count(goal: GoalKu) -> int:
            """Get count of blocked knowledge prerequisites for sorting."""
            return len(goal.metadata.get("blocked_by_knowledge", []))

        blocked_goals.sort(key=get_blocked_knowledge_count)

        result_goals = blocked_goals[:limit]

        self.logger.info(
            f"Found {len(result_goals)} goals blocked by knowledge for user {user_context.user_uid}"
        )
        return Result.ok(result_goals)

    # list_categories() - inherited from BaseService (uses _category_field = "domain")

    async def get_goals_for_task(self, task_uid: str) -> Result[list[GoalKu]]:
        """
        Get goals that a task fulfills.

        Query: (Task)-[:FULFILLS_GOAL]->(Goal)

        Args:
            task_uid: Task UID

        Returns:
            Result containing goals the task contributes to
        """
        try:
            return await self.get_by_relationship(
                related_uid=task_uid,
                relationship_type=RelationshipName.FULFILLS_GOAL,
                direction="outgoing",
            )

        except Exception as e:
            self.logger.error(f"Get goals for task failed: {e}")
            return Result.fail(Errors.database(operation="get_goals_for_task", message=str(e)))

    async def get_goals_for_habit(self, habit_uid: str) -> Result[list[GoalKu]]:
        """
        Get goals that a habit supports.

        Query: (Habit)-[:SUPPORTS_GOAL]->(Goal)

        Args:
            habit_uid: Habit UID

        Returns:
            Result containing goals the habit supports
        """
        try:
            return await self.get_by_relationship(
                related_uid=habit_uid,
                relationship_type=RelationshipName.SUPPORTS_GOAL,
                direction="outgoing",
            )

        except Exception as e:
            self.logger.error(f"Get goals for habit failed: {e}")
            return Result.fail(Errors.database(operation="get_goals_for_habit", message=str(e)))

    async def get_sub_goals(self, parent_goal_uid: str) -> Result[list[GoalKu]]:
        """
        Get child goals (sub-goals) of a parent goal.

        Query: (ChildGoal)-[:SUBGOAL_OF]->(ParentGoal)

        Args:
            parent_goal_uid: Parent goal UID

        Returns:
            Result containing sub-goals
        """
        try:
            return await self.get_by_relationship(
                related_uid=parent_goal_uid,
                relationship_type=RelationshipName.SUBGOAL_OF,
                direction="incoming",
            )

        except Exception as e:
            self.logger.error(f"Get sub goals failed: {e}")
            return Result.fail(Errors.database(operation="get_sub_goals", message=str(e)))

    @with_error_handling("get_related_goals", error_type="database", uid_param="goal_uid")
    async def get_related_goals(self, goal_uid: str, limit: int = 10) -> Result[list[GoalKu]]:
        """
        Get goals related to a given goal (shared tasks, habits, or knowledge).

        Args:
            goal_uid: Goal UID to find related goals for
            limit: Maximum results to return

        Returns:
            Result containing related goals
        """
        # Query for goals sharing tasks or habits
        cypher_query = """
        MATCH (g:Ku {uid: $uid, ku_type: 'goal'})<-[:FULFILLS_GOAL|SUPPORTS_GOAL]-(shared)-[:FULFILLS_GOAL|SUPPORTS_GOAL]->(related:Ku {ku_type: 'goal'})
        WHERE related <> g
        RETURN DISTINCT related as g, count(shared) as shared_count
        ORDER BY shared_count DESC
        LIMIT $limit
        """

        result = await self.backend.execute_query(cypher_query, {"uid": goal_uid, "limit": limit})
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Goals
        goals = []
        for record in result.value:
            goal_node = record["g"]
            dto = KuDTO.from_dict(dict(goal_node))
            goal = GoalKu.from_dto(dto)
            # Store shared count in metadata
            goal.metadata["shared_count"] = record.get("shared_count", 0)
            goals.append(goal)

        self.logger.debug(f"Found {len(goals)} goals related to {goal_uid}")
        return Result.ok(goals)

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
    ) -> Result[tuple[list[GoalKu], ParsedSearchQuery]]:
        """
        Natural language search with semantic filter extraction.

        Parses queries like "weekly health goals achieved" to extract:
        - Timeframe filters (weekly → WEEKLY)
        - Status filters (achieved → ACHIEVED)
        - Domain filters (health → HEALTH)
        - Priority filters (urgent → CRITICAL/HIGH)

        Args:
            query: Natural language search query
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing (goals, parsed_query) tuple

        Example:
            >>> result = await search.intelligent_search("monthly tech goals in progress")
            >>> goals, parsed = result.value
            >>> print(f"Filters: {parsed.to_filter_summary()}")
        """
        # Parse query for semantic filters
        parser = SearchQueryParser()
        parsed = parser.parse(query)
        query_lower = query.lower()

        # Build filters from parsed query
        filters: dict[str, object] = {}

        # Goal-specific: Timeframe extraction
        # GoalTimeframe: DAILY, WEEKLY, MONTHLY, QUARTERLY, YEARLY, MULTI_YEAR
        timeframe_keywords = {
            "daily": GoalTimeframe.DAILY,
            "weekly": GoalTimeframe.WEEKLY,
            "monthly": GoalTimeframe.MONTHLY,
            "quarterly": GoalTimeframe.QUARTERLY,
            "yearly": GoalTimeframe.YEARLY,
            "annual": GoalTimeframe.YEARLY,
            "life": GoalTimeframe.MULTI_YEAR,  # Closest to "life" goals
            "lifetime": GoalTimeframe.MULTI_YEAR,
            "long term": GoalTimeframe.MULTI_YEAR,
        }
        for keyword, timeframe in timeframe_keywords.items():
            if keyword in query_lower:
                filters["timeframe"] = timeframe.value
                break

        # Goal-specific: Status extraction
        # KuStatus: DRAFT, ACTIVE, PAUSED, COMPLETED, CANCELLED, FAILED, ARCHIVED
        status_keywords = {
            "achieved": KuStatus.COMPLETED,
            "completed": KuStatus.COMPLETED,
            "active": KuStatus.ACTIVE,
            "in progress": KuStatus.ACTIVE,  # Maps to ACTIVE
            "in_progress": KuStatus.ACTIVE,
            "on track": KuStatus.ACTIVE,  # Maps to ACTIVE
            "paused": KuStatus.PAUSED,
            "on hold": KuStatus.PAUSED,
            "abandoned": KuStatus.CANCELLED,  # Maps to CANCELLED
            "cancelled": KuStatus.CANCELLED,
            "failed": KuStatus.FAILED,
            "planned": KuStatus.DRAFT,
        }
        for keyword, status in status_keywords.items():
            if keyword in query_lower:
                filters["status"] = status.value
                break

        # Apply priority filter from parsed query (use highest priority if multiple)
        if parsed.priorities:
            highest_priority = parsed.get_highest_priority()
            if highest_priority:
                filters["priority"] = highest_priority.value

        # Apply domain filter from parsed query (use first domain if multiple)
        if parsed.domains:
            filters["domain"] = parsed.domains[0].value

        # Execute search
        if filters:
            # Use filtered search via backend
            result = await self.backend.find_by(limit=limit, **filters)
            if result.is_error:
                return Result.fail(result.expect_error())
            goals = self._to_domain_models(result.value, KuDTO, GoalKu)
        else:
            # Fall back to text search using cleaned query
            result = await self.search(parsed.text_query, limit=limit)
            if result.is_error:
                return Result.fail(result.expect_error())
            goals = result.value

        # Filter by user ownership if provided
        if user_uid and goals:
            goals = [g for g in goals if getattr(g, "user_uid", None) == user_uid]

        self.logger.info(
            "Intelligent search: query=%r filters=%s results=%d",
            query,
            parsed.to_filter_summary(),
            len(goals),
        )

        return Result.ok((goals, parsed))
