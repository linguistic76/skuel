"""
Submissions Search Service
============================

Service for querying submissions across all types.

Core Capabilities:
- Query submissions by type, date range, status
- Filter by metadata (category, mood, tags)
- Search submission content
- Calculate statistics (streaks, word count, etc.)
"""

from datetime import date, timedelta
from typing import Any, ClassVar

from core.constants import QueryLimit
from core.models.entity import Entity
from core.models.entity_types import SubmissionEntity
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.submissions.submission_dto import SubmissionDTO
from core.models.type_hints import UserUID
from core.ports import BackendOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.submissions_search")


class SubmissionsSearchService(BaseService[BackendOperations[Entity], Entity]):
    """
    Submissions search service — unified interface for all submission types.

    Provides queries for submissions of any type:
    - Get submission for specific date
    - List submissions by date range
    - Filter by type, category, mood, tags
    - Calculate statistics (streaks, word count)
    - Search submission content

    Does NOT handle:
    - File uploads (use SubmissionsService)
    - Audio processing (use TranscriptionService)
    - Content processing (use SubmissionsProcessingService)
    - Learning loop queries that traverse Interaction/Exercise/Report edges
      (use LearningLoopQueryService)
    """

    # =========================================================================
    # DomainConfig
    # =========================================================================
    _config = DomainConfig(
        dto_class=SubmissionDTO,
        model_class=Entity,
        entity_label="Entity",
        search_fields=("title", "original_filename", "processed_content"),
        search_order_by="created_at",
        category_field="entity_type",
        user_ownership_relationship=RelationshipName.OWNS,
    )

    # Graph enrichment for graph_aware_faceted_search (SearchRouter integration)
    _graph_enrichment_patterns: ClassVar[
        tuple[tuple[str, str, str] | tuple[str, str, str, str], ...]
    ] = (
        (RelationshipName.FULFILLS_EXERCISE.value, NeoLabel.ENTITY.value, "fulfills_exercise"),
        (
            RelationshipName.REPORT_FOR.value,
            NeoLabel.ENTITY.value,
            "reports_received",
            "incoming",
        ),
    )

    def __init__(
        self, submissions_backend: BackendOperations[SubmissionEntity], event_bus=None
    ) -> None:
        """
        Initialize submissions search service.

        Args:
            submissions_backend: Backend for submission storage
            event_bus: Event bus for domain events (optional)
        """
        super().__init__(submissions_backend, "SubmissionsSearchService")
        self.event_bus = event_bus
        self.logger = logger  # type: ignore[assignment]  # structlog BoundLogger

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Entity nodes."""
        return "Entity"

    # ========================================================================
    # SUBMISSION QUERIES
    # ========================================================================

    @with_error_handling("get_report_for_date")
    async def get_report_for_date(
        self,
        user_uid: UserUID,
        target_date: date,
        entity_type: EntityType | None = None,
    ) -> Result[Entity | None]:
        """
        Get submission for a specific date.

        Args:
            user_uid: User identifier
            target_date: Date to search for
            entity_type: Optional type filter

        Returns:
            Result containing submission or None if not found
        """
        filters: dict[str, Any] = {"user_uid": user_uid, "limit": 1}
        if entity_type:
            filters["entity_type"] = entity_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return Result.fail(result)

        submissions = result.value

        for submission in submissions:
            if submission.created_at.date() == target_date:
                return Result.ok(submission)

        return Result.ok(None)

    @with_error_handling("list_reports_by_date_range")
    async def list_reports_by_date_range(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        entity_type: EntityType | None = None,
        limit: int = 100,
    ) -> Result[list[Entity]]:
        """
        List submissions within a date range.

        Args:
            user_uid: User identifier
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            entity_type: Optional type filter
            limit: Max results (default 100)

        Returns:
            Result containing list of submissions
        """
        filters: dict[str, Any] = {
            "user_uid": user_uid,
            "limit": limit,
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if entity_type:
            filters["entity_type"] = entity_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return result

        reports = result.value
        filtered = [k for k in reports if start_date <= k.created_at.date() <= end_date]

        return Result.ok(filtered)

    @with_error_handling("get_reports_by_category")
    async def get_reports_by_category(
        self,
        user_uid: UserUID,
        category: str,
        entity_type: EntityType | None = None,
        limit: int = 50,
    ) -> Result[list[Entity]]:
        """
        Get submissions filtered by category (stored in metadata).

        Args:
            user_uid: User identifier
            category: Category name
            entity_type: Optional type filter
            limit: Max results

        Returns:
            Result containing list of submissions
        """
        filters: dict[str, Any] = {
            "user_uid": user_uid,
            "limit": limit * 2,
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if entity_type:
            filters["entity_type"] = entity_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return result

        reports = result.value
        filtered = [k for k in reports if k.metadata and k.metadata.get("category") == category][
            :limit
        ]

        return Result.ok(filtered)

    @with_error_handling("get_reports_by_mood")
    async def get_reports_by_mood(
        self,
        user_uid: UserUID,
        mood: str,
        start_date: date | None = None,
        end_date: date | None = None,
        entity_type: EntityType | None = None,
        limit: int = 50,
    ) -> Result[list[Entity]]:
        """
        Get submissions filtered by mood (stored in metadata).

        Args:
            user_uid: User identifier
            mood: Mood name
            start_date: Optional start date filter
            end_date: Optional end date filter
            entity_type: Optional type filter
            limit: Max results

        Returns:
            Result containing list of submissions
        """
        filters: dict[str, Any] = {
            "user_uid": user_uid,
            "limit": limit * 2,
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if entity_type:
            filters["entity_type"] = entity_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return result

        reports = result.value

        filtered = []
        for k in reports:
            if not k.metadata or k.metadata.get("mood") != mood:
                continue
            if start_date and k.created_at.date() < start_date:
                continue
            if end_date and k.created_at.date() > end_date:
                continue
            filtered.append(k)
            if len(filtered) >= limit:
                break

        return Result.ok(filtered)

    @with_error_handling("search_submissions")
    async def search_submissions(
        self,
        user_uid: UserUID,
        query: str,
        entity_type: EntityType | None = None,
        limit: int = 50,
    ) -> Result[list[Entity]]:
        """
        Search submission content using text search.

        Searches in processed_content field.

        Args:
            user_uid: User identifier
            query: Search query string
            entity_type: Optional type filter
            limit: Max results

        Returns:
            Result containing list of matching submissions
        """
        filters: dict[str, Any] = {
            "user_uid": user_uid,
            "limit": limit * 3,
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if entity_type:
            filters["entity_type"] = entity_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return result

        reports = result.value
        query_lower = query.lower()

        def _has_matching_content(k: Entity) -> bool:
            pc = getattr(k, "processed_content", None)
            return bool(pc and query_lower in pc.lower())

        filtered = [k for k in reports if _has_matching_content(k)][:limit]

        return Result.ok(filtered)

    @with_error_handling("get_submissions_with_feedback_status")
    async def get_submissions_with_feedback_status(
        self,
        user_uid: UserUID,
        limit: int = 50,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get a student's submissions enriched with teacher feedback status.

        Returns each SUBMISSION entity alongside its REPORT_FOR report count,
        enabling the UI to show review badges without N+1 queries.

        Args:
            user_uid: Student user UID
            limit: Max results (default 50)

        Returns:
            Result containing list of dicts with uid, title, original_filename,
            status, entity_type, created_at, and feedback_count.
        """
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(s:Entity)
        WHERE s.entity_type = $submission_type
        OPTIONAL MATCH (fb:Entity {{entity_type: $report_type}})-[:{RelationshipName.REPORT_FOR.value}]->(s)
        WITH s, count(fb) AS feedback_count
        RETURN s.uid AS uid,
               s.title AS title,
               s.original_filename AS original_filename,
               s.status AS status,
               s.entity_type AS entity_type,
               s.created_at AS created_at,
               feedback_count
        ORDER BY s.created_at DESC
        LIMIT $limit
        """

        result = await self.backend.execute_query(
            query,
            {
                "user_uid": user_uid,
                "limit": limit,
                "submission_type": EntityType.EXERCISE_SUBMISSION.value,
                "report_type": EntityType.EXERCISE_REPORT.value,
            },
        )
        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            [
                {
                    "uid": record["uid"],
                    "title": record.get("title"),
                    "original_filename": record.get("original_filename"),
                    "status": record.get("status"),
                    "entity_type": record.get("entity_type"),
                    "created_at": record.get("created_at"),
                    "feedback_count": record.get("feedback_count") or 0,
                }
                for record in result.value or []
            ]
        )

    # ========================================================================
    # STATISTICS
    # ========================================================================

    @with_error_handling("get_report_statistics")
    async def get_report_statistics(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        entity_type: EntityType | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Calculate submission statistics for date range.

        Statistics include:
        - Total submissions
        - Total words written
        - Average words per submission
        - Longest streak (consecutive days)
        - Current streak
        - Most productive day of week
        - Category distribution
        - Type distribution (if not filtered)
        """
        reports_result = await self.list_reports_by_date_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            entity_type=entity_type,
            limit=QueryLimit.COMPREHENSIVE,
        )

        if reports_result.is_error:
            return Result.fail(reports_result)

        reports = reports_result.value

        total_reports = len(reports)
        if total_reports == 0:
            return Result.ok(
                {
                    "total_reports": 0,
                    "total_words": 0,
                    "average_words": 0,
                    "longest_streak": 0,
                    "current_streak": 0,
                    "kus_by_day_of_week": {},
                    "kus_by_category": {},
                    "kus_by_type": {},
                }
            )

        # Total words
        def _word_count(k: Entity) -> int:
            pc = getattr(k, "processed_content", None)
            return len(pc.split()) if pc else 0

        total_words = sum(_word_count(k) for k in reports)
        average_words = total_words / total_reports if total_reports > 0 else 0

        # Streak calculation
        report_dates = sorted([k.created_at.date() for k in reports])
        longest_streak = self._calculate_longest_streak(report_dates)
        current_streak = self._calculate_current_streak(report_dates)

        # Day of week distribution
        day_of_week_counts: dict[str, int] = {}
        for k in reports:
            day_name = k.created_at.strftime("%A")
            day_of_week_counts[day_name] = day_of_week_counts.get(day_name, 0) + 1

        # Category distribution
        category_counts: dict[str, int] = {}
        for k in reports:
            if k.metadata and "category" in k.metadata:
                category = k.metadata["category"]
                category_counts[category] = category_counts.get(category, 0) + 1

        # Type distribution
        type_counts: dict[str, int] = {}
        if not entity_type:
            for k in reports:
                type_name = k.entity_type.value
                type_counts[type_name] = type_counts.get(type_name, 0) + 1

        return Result.ok(
            {
                "total_reports": total_reports,
                "total_words": total_words,
                "average_words": round(average_words, 1),
                "longest_streak": longest_streak,
                "current_streak": current_streak,
                "kus_by_day_of_week": day_of_week_counts,
                "kus_by_category": category_counts,
                "kus_by_type": type_counts,
            }
        )

    def _calculate_longest_streak(self, dates: list[date]) -> int:
        """Calculate longest consecutive day streak."""
        if not dates:
            return 0

        longest = 1
        current = 1

        for i in range(1, len(dates)):
            delta = (dates[i] - dates[i - 1]).days
            if delta == 1:
                current += 1
                longest = max(longest, current)
            elif delta > 1:
                current = 1

        return longest

    def _calculate_current_streak(self, dates: list[date]) -> int:
        """Calculate current consecutive day streak ending today."""
        if not dates:
            return 0

        today = date.today()
        yesterday = today - timedelta(days=1)

        last_date = dates[-1]
        if last_date not in {today, yesterday}:
            return 0

        streak = 1
        for i in range(len(dates) - 2, -1, -1):
            delta = (dates[i + 1] - dates[i]).days
            if delta == 1:
                streak += 1
            else:
                break

        return streak

    # ========================================================================
    # RECENT SUBMISSIONS
    # ========================================================================

    @with_error_handling("get_recent_submissions")
    async def get_recent_submissions(
        self,
        user_uid: UserUID,
        entity_type: EntityType | None = None,
        limit: int = 10,
    ) -> Result[list[Entity]]:
        """
        Get most recent submissions.

        Args:
            user_uid: User identifier
            entity_type: Optional type filter
            limit: Max results (default 10)

        Returns:
            Result containing list of recent submissions
        """
        filters: dict[str, Any] = {
            "user_uid": user_uid,
            "limit": limit,
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if entity_type:
            filters["entity_type"] = entity_type.value

        return await self.backend.find_by(**filters)
