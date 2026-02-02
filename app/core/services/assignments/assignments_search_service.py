"""
Assignments Query Service
==========================

Service for querying assignments across all types (transcripts, reports, etc.).

Core Capabilities:
- Query assignments by type, date range, status
- Filter by metadata (category, mood, tags)
- Search assignment content
- Calculate statistics (streaks, word count, etc.)

Assignment Types Supported:
- TRANSCRIPT: Meeting notes and transcriptions
- REPORT: Formal reports and documentation
- IMAGE_ANALYSIS: Visual content analysis
- VIDEO_SUMMARY: Video content summaries

This service provides a unified query interface for the Assignments domain.
It operates on Assignment nodes regardless of their specific type.
"""

from datetime import date, timedelta
from typing import Any

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.constants import QueryLimit
from core.models.assignment.assignment import Assignment, AssignmentDTO, AssignmentType
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.services.protocols import BackendOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.assignments_query")


class AssignmentsQueryService(BaseService[BackendOperations[Assignment], Assignment]):
    """
    Assignments query service - unified interface for all assignment types.

    Provides queries for assignments of any type:
    - Get assignment for specific date
    - List assignments by date range
    - Filter by type, category, mood, tags
    - Calculate statistics (streaks, word count)
    - Search assignment content

    Supports Assignment types:
    - Transcripts
    - Reports
    - Image analysis
    - Video summaries

    Does NOT handle:
    - File uploads (use AssignmentSubmissionService)
    - Audio processing (use TranscriptionService)
    - Content processing (use AssignmentProcessorService)
    - AI formatting (use TranscriptProcessorService)
    """

    # =========================================================================
    # DomainConfig (January 2026 Phase 3)
    # =========================================================================
    _config = DomainConfig(
        dto_class=AssignmentDTO,
        model_class=Assignment,
        entity_label="Assignment",
        search_fields=("original_filename", "processed_title", "processed_content"),
        search_order_by="submitted_at",
        category_field="assignment_type",
        user_ownership_relationship="OWNS",  # User-owned content
    )

    def __init__(
        self, assignment_backend: UniversalNeo4jBackend[Assignment], event_bus=None
    ) -> None:
        """
        Initialize assignments query service.

        Args:
            assignment_backend: UniversalNeo4jBackend[Assignment] for storage
            event_bus: Event bus for domain events (optional)
        """
        super().__init__(assignment_backend, "AssignmentsQueryService")
        self.event_bus = event_bus
        self.logger = logger

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Assignment entities."""
        return "Assignment"

    # ========================================================================
    # ASSIGNMENT QUERIES (Generalized)
    # ========================================================================

    @with_error_handling("get_assignment_for_date")
    async def get_assignment_for_date(
        self,
        user_uid: str,
        target_date: date,
        assignment_type: AssignmentType | None = None,
    ) -> Result[Assignment | None]:
        """
        Get assignment for a specific date.

        Searches for assignments with:
        - user_uid = user_uid
        - created_at date matches target_date
        - assignment_type = assignment_type (if provided)

        Args:
            user_uid: User identifier
            target_date: Date to search for
            assignment_type: Optional type filter (JOURNAL, ESSAY, etc.)

        Returns:
            Result containing assignment or None if not found
        """
        # Build query filters
        filters = {"user_uid": user_uid, "limit": 1}
        if assignment_type:
            filters["assignment_type"] = assignment_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return Result.fail(result)

        assignments = result.value

        # Filter by date in Python (Neo4j datetime comparison is complex)
        for assignment in assignments:
            if assignment.created_at.date() == target_date:
                return Result.ok(assignment)

        return Result.ok(None)

    @with_error_handling("list_assignments_by_date_range")
    async def list_assignments_by_date_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        assignment_type: AssignmentType | None = None,
        limit: int = 100,
    ) -> Result[list[Assignment]]:
        """
        List assignments within a date range.

        Args:
            user_uid: User identifier
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            assignment_type: Optional type filter (JOURNAL, ESSAY, etc.)
            limit: Max results (default 100)

        Returns:
            Result containing list of assignments
        """
        # Build query filters
        filters = {
            "user_uid": user_uid,
            "limit": limit,
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if assignment_type:
            filters["assignment_type"] = assignment_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return result

        assignments = result.value

        # Filter by date range in Python
        filtered = [a for a in assignments if start_date <= a.created_at.date() <= end_date]

        return Result.ok(filtered)

    @with_error_handling("get_assignments_by_category")
    async def get_assignments_by_category(
        self,
        user_uid: str,
        category: str,
        assignment_type: AssignmentType | None = None,
        limit: int = 50,
    ) -> Result[list[Assignment]]:
        """
        Get assignments filtered by category.

        Categories are stored in assignment metadata.

        Args:
            user_uid: User identifier
            category: Category name (e.g., "personal", "work", "reflection", "research")
            assignment_type: Optional type filter (JOURNAL, ESSAY, etc.)
            limit: Max results

        Returns:
            Result containing list of assignments
        """
        # Build query filters
        filters = {
            "user_uid": user_uid,
            "limit": limit * 2,  # Fetch more to account for filtering
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if assignment_type:
            filters["assignment_type"] = assignment_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return result

        assignments = result.value

        # Filter by category in metadata
        filtered = [
            a for a in assignments if a.metadata and a.metadata.get("category") == category
        ][:limit]

        return Result.ok(filtered)

    @with_error_handling("get_assignments_by_mood")
    async def get_assignments_by_mood(
        self,
        user_uid: str,
        mood: str,
        start_date: date | None = None,
        end_date: date | None = None,
        assignment_type: AssignmentType | None = None,
        limit: int = 50,
    ) -> Result[list[Assignment]]:
        """
        Get assignments filtered by mood.

        Moods are extracted during processing and stored in metadata.

        Args:
            user_uid: User identifier
            mood: Mood name (e.g., "happy", "reflective", "stressed", "focused")
            start_date: Optional start date filter
            end_date: Optional end date filter
            assignment_type: Optional type filter (JOURNAL, ESSAY, etc.)
            limit: Max results

        Returns:
            Result containing list of assignments
        """
        # Build query filters
        filters = {
            "user_uid": user_uid,
            "limit": limit * 2,  # Fetch more to account for filtering
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if assignment_type:
            filters["assignment_type"] = assignment_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return result

        assignments = result.value

        # Filter by mood in metadata
        filtered = []
        for a in assignments:
            if not a.metadata or a.metadata.get("mood") != mood:
                continue

            # Apply date filters if provided
            if start_date and a.created_at.date() < start_date:
                continue
            if end_date and a.created_at.date() > end_date:
                continue

            filtered.append(a)

            if len(filtered) >= limit:
                break

        return Result.ok(filtered)

    @with_error_handling("search_assignments")
    async def search_assignments(
        self,
        user_uid: str,
        query: str,
        assignment_type: AssignmentType | None = None,
        limit: int = 50,
    ) -> Result[list[Assignment]]:
        """
        Search assignment content using text search.

        Searches in processed_content field.

        Args:
            user_uid: User identifier
            query: Search query string
            assignment_type: Optional type filter (JOURNAL, ESSAY, etc.)
            limit: Max results

        Returns:
            Result containing list of matching assignments
        """
        # Build query filters
        filters = {
            "user_uid": user_uid,
            "limit": limit * 3,  # Fetch more to account for filtering
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if assignment_type:
            filters["assignment_type"] = assignment_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return result

        assignments = result.value

        # Filter by content search (simple substring match)
        query_lower = query.lower()
        filtered = [
            a
            for a in assignments
            if a.processed_content and query_lower in a.processed_content.lower()
        ][:limit]

        return Result.ok(filtered)

    # ========================================================================
    # STATISTICS (Generalized)
    # ========================================================================

    @with_error_handling("get_assignment_statistics")
    async def get_assignment_statistics(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        assignment_type: AssignmentType | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Calculate assignment statistics for date range.

        Statistics include:
        - Total assignments submitted
        - Total words written
        - Average words per assignment
        - Longest streak (consecutive days)
        - Current streak
        - Most productive day of week
        - Category distribution
        - Type distribution (if not filtered)

        Args:
            user_uid: User identifier
            start_date: Start date for analysis
            end_date: End date for analysis
            assignment_type: Optional type filter (JOURNAL, ESSAY, etc.)

        Returns:
            Result containing statistics dictionary
        """
        # Get all assignments in date range
        assignments_result = await self.list_assignments_by_date_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            assignment_type=assignment_type,
            limit=QueryLimit.COMPREHENSIVE,  # Large enough for most use cases
        )

        if assignments_result.is_error:
            return Result.fail(assignments_result.expect_error())

        assignments = assignments_result.value

        # Calculate statistics
        total_assignments = len(assignments)
        if total_assignments == 0:
            return Result.ok(
                {
                    "total_assignments": 0,
                    "total_words": 0,
                    "average_words": 0,
                    "longest_streak": 0,
                    "current_streak": 0,
                    "assignments_by_day_of_week": {},
                    "assignments_by_category": {},
                    "assignments_by_type": {},
                }
            )

        # Total words
        total_words = sum(
            len(a.processed_content.split()) if a.processed_content else 0 for a in assignments
        )
        average_words = total_words / total_assignments if total_assignments > 0 else 0

        # Streak calculation
        assignment_dates = sorted([a.created_at.date() for a in assignments])
        longest_streak = self._calculate_longest_streak(assignment_dates)
        current_streak = self._calculate_current_streak(assignment_dates)

        # Day of week distribution
        day_of_week_counts = {}
        for a in assignments:
            day_name = a.created_at.strftime("%A")
            day_of_week_counts[day_name] = day_of_week_counts.get(day_name, 0) + 1

        # Category distribution
        category_counts = {}
        for a in assignments:
            if a.metadata and "category" in a.metadata:
                category = a.metadata["category"]
                category_counts[category] = category_counts.get(category, 0) + 1

        # Type distribution (only if not filtered by type)
        type_counts = {}
        if not assignment_type:
            for a in assignments:
                type_name = a.assignment_type.value
                type_counts[type_name] = type_counts.get(type_name, 0) + 1

        return Result.ok(
            {
                "total_assignments": total_assignments,
                "total_words": total_words,
                "average_words": round(average_words, 1),
                "longest_streak": longest_streak,
                "current_streak": current_streak,
                "assignments_by_day_of_week": day_of_week_counts,
                "assignments_by_category": category_counts,
                "assignments_by_type": type_counts,
            }
        )

    def _calculate_longest_streak(self, dates: list[date]) -> int:
        """Calculate longest consecutive day streak"""
        if not dates:
            return 0

        longest = 1
        current = 1

        for i in range(1, len(dates)):
            # Check if consecutive days
            delta = (dates[i] - dates[i - 1]).days
            if delta == 1:
                current += 1
                longest = max(longest, current)
            elif delta > 1:
                current = 1

        return longest

    def _calculate_current_streak(self, dates: list[date]) -> int:
        """Calculate current consecutive day streak ending today"""
        if not dates:
            return 0

        today = date.today()
        yesterday = today - timedelta(days=1)

        # Check if last assignment was today or yesterday
        last_date = dates[-1]
        if last_date not in {today, yesterday}:
            return 0

        # Count backwards
        streak = 1
        for i in range(len(dates) - 2, -1, -1):
            delta = (dates[i + 1] - dates[i]).days
            if delta == 1:
                streak += 1
            else:
                break

        return streak

    # ========================================================================
    # RECENT ASSIGNMENTS
    # ========================================================================

    @with_error_handling("get_recent_assignments")
    async def get_recent_assignments(
        self,
        user_uid: str,
        assignment_type: AssignmentType | None = None,
        limit: int = 10,
    ) -> Result[list[Assignment]]:
        """
        Get most recent assignments.

        Args:
            user_uid: User identifier
            assignment_type: Optional type filter (JOURNAL, ESSAY, etc.)
            limit: Max results (default 10)

        Returns:
            Result containing list of recent assignments
        """
        # Build query filters
        filters = {
            "user_uid": user_uid,
            "limit": limit,
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if assignment_type:
            filters["assignment_type"] = assignment_type.value

        return await self.backend.find_by(**filters)

    # ========================================================================
    # CROSS-DOMAIN QUERIES
    # ========================================================================

    @with_error_handling("get_journal_for_assignment")
    async def get_journal_for_assignment(
        self,
        assignment_uid: str,
        user_uid: str,
    ) -> Result[dict[str, Any] | None]:
        """
        Get the Journal created from processing this assignment.

        Journals store source assignment UID in metadata.source_assignment_uid.
        This is a cross-domain query serving the Assignment use case.

        Args:
            assignment_uid: The assignment UID to find journal for
            user_uid: User UID for ownership verification

        Returns:
            Result containing journal dict {uid, content, metadata, created_at} or None
        """
        driver = self.backend.driver

        cypher = """
        MATCH (j:Journal {user_uid: $user_uid})
        WHERE j.metadata IS NOT NULL
          AND j.metadata CONTAINS $assignment_uid
        RETURN j.uid as uid, j.content as content,
               j.metadata as metadata, j.created_at as created_at
        ORDER BY j.created_at DESC
        LIMIT 1
        """

        async with driver.session() as session:
            result = await session.run(cypher, user_uid=user_uid, assignment_uid=assignment_uid)
            records = [r async for r in result]

            if records:
                record = records[0]
                return Result.ok(
                    {
                        "uid": record["uid"],
                        "content": record["content"],
                        "metadata": record["metadata"],
                        "created_at": record["created_at"],
                    }
                )

            return Result.ok(None)
