"""
Reports Search Service
==========================

Service for querying reports across all types (transcripts, reports, etc.).

Core Capabilities:
- Query reports by type, date range, status
- Filter by metadata (category, mood, tags)
- Search report content
- Calculate statistics (streaks, word count, etc.)

Report Types Supported:
- TRANSCRIPT: Meeting notes and transcriptions
- REPORT: Formal reports and documentation
- IMAGE_ANALYSIS: Visual content analysis
- VIDEO_SUMMARY: Video content summaries

This service provides a unified query interface for the Reports domain.
It operates on Report nodes regardless of their specific type.
"""

from datetime import date, timedelta
from typing import Any

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.constants import QueryLimit
from core.models.report.report import Report, ReportDTO, ReportType
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.services.protocols import BackendOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.reports_search")


class ReportsSearchService(BaseService[BackendOperations[Report], Report]):
    """
    Reports search service - unified interface for all report types.

    Provides queries for reports of any type:
    - Get report for specific date
    - List reports by date range
    - Filter by type, category, mood, tags
    - Calculate statistics (streaks, word count)
    - Search report content

    Supports Report types:
    - Transcripts
    - Reports
    - Image analysis
    - Video summaries

    Does NOT handle:
    - File uploads (use ReportSubmissionService)
    - Audio processing (use TranscriptionService)
    - Content processing (use ReportsProcessingService)
    - AI formatting (use TranscriptProcessorService)
    """

    # =========================================================================
    # DomainConfig (January 2026 Phase 3)
    # =========================================================================
    _config = DomainConfig(
        dto_class=ReportDTO,
        model_class=Report,
        entity_label="Report",
        search_fields=("original_filename", "processed_title", "processed_content"),
        search_order_by="submitted_at",
        category_field="report_type",
        user_ownership_relationship="OWNS",  # User-owned content
    )

    def __init__(self, report_backend: UniversalNeo4jBackend[Report], event_bus=None) -> None:
        """
        Initialize reports search service.

        Args:
            report_backend: UniversalNeo4jBackend[Report] for storage
            event_bus: Event bus for domain events (optional)
        """
        super().__init__(report_backend, "ReportsSearchService")
        self.event_bus = event_bus
        self.logger = logger

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Report entities."""
        return "Report"

    # ========================================================================
    # REPORT QUERIES (Generalized)
    # ========================================================================

    @with_error_handling("get_report_for_date")
    async def get_report_for_date(
        self,
        user_uid: str,
        target_date: date,
        report_type: ReportType | None = None,
    ) -> Result[Report | None]:
        """
        Get report for a specific date.

        Searches for reports with:
        - user_uid = user_uid
        - created_at date matches target_date
        - report_type = report_type (if provided)

        Args:
            user_uid: User identifier
            target_date: Date to search for
            report_type: Optional type filter (JOURNAL, ESSAY, etc.)

        Returns:
            Result containing report or None if not found
        """
        # Build query filters
        filters = {"user_uid": user_uid, "limit": 1}
        if report_type:
            filters["report_type"] = report_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return Result.fail(result)

        reports = result.value

        # Filter by date in Python (Neo4j datetime comparison is complex)
        for report in reports:
            if report.created_at.date() == target_date:
                return Result.ok(report)

        return Result.ok(None)

    @with_error_handling("list_reports_by_date_range")
    async def list_reports_by_date_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        report_type: ReportType | None = None,
        limit: int = 100,
    ) -> Result[list[Report]]:
        """
        List reports within a date range.

        Args:
            user_uid: User identifier
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            report_type: Optional type filter (JOURNAL, ESSAY, etc.)
            limit: Max results (default 100)

        Returns:
            Result containing list of reports
        """
        # Build query filters
        filters = {
            "user_uid": user_uid,
            "limit": limit,
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if report_type:
            filters["report_type"] = report_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return result

        reports = result.value

        # Filter by date range in Python
        filtered = [a for a in reports if start_date <= a.created_at.date() <= end_date]

        return Result.ok(filtered)

    @with_error_handling("get_reports_by_category")
    async def get_reports_by_category(
        self,
        user_uid: str,
        category: str,
        report_type: ReportType | None = None,
        limit: int = 50,
    ) -> Result[list[Report]]:
        """
        Get reports filtered by category.

        Categories are stored in report metadata.

        Args:
            user_uid: User identifier
            category: Category name (e.g., "personal", "work", "reflection", "research")
            report_type: Optional type filter (JOURNAL, ESSAY, etc.)
            limit: Max results

        Returns:
            Result containing list of reports
        """
        # Build query filters
        filters = {
            "user_uid": user_uid,
            "limit": limit * 2,  # Fetch more to account for filtering
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if report_type:
            filters["report_type"] = report_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return result

        reports = result.value

        # Filter by category in metadata
        filtered = [a for a in reports if a.metadata and a.metadata.get("category") == category][
            :limit
        ]

        return Result.ok(filtered)

    @with_error_handling("get_reports_by_mood")
    async def get_reports_by_mood(
        self,
        user_uid: str,
        mood: str,
        start_date: date | None = None,
        end_date: date | None = None,
        report_type: ReportType | None = None,
        limit: int = 50,
    ) -> Result[list[Report]]:
        """
        Get reports filtered by mood.

        Moods are extracted during processing and stored in metadata.

        Args:
            user_uid: User identifier
            mood: Mood name (e.g., "happy", "reflective", "stressed", "focused")
            start_date: Optional start date filter
            end_date: Optional end date filter
            report_type: Optional type filter (JOURNAL, ESSAY, etc.)
            limit: Max results

        Returns:
            Result containing list of reports
        """
        # Build query filters
        filters = {
            "user_uid": user_uid,
            "limit": limit * 2,  # Fetch more to account for filtering
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if report_type:
            filters["report_type"] = report_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return result

        reports = result.value

        # Filter by mood in metadata
        filtered = []
        for a in reports:
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

    @with_error_handling("search_reports")
    async def search_reports(
        self,
        user_uid: str,
        query: str,
        report_type: ReportType | None = None,
        limit: int = 50,
    ) -> Result[list[Report]]:
        """
        Search report content using text search.

        Searches in processed_content field.

        Args:
            user_uid: User identifier
            query: Search query string
            report_type: Optional type filter (JOURNAL, ESSAY, etc.)
            limit: Max results

        Returns:
            Result containing list of matching reports
        """
        # Build query filters
        filters = {
            "user_uid": user_uid,
            "limit": limit * 3,  # Fetch more to account for filtering
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if report_type:
            filters["report_type"] = report_type.value

        result = await self.backend.find_by(**filters)

        if result.is_error:
            return result

        reports = result.value

        # Filter by content search (simple substring match)
        query_lower = query.lower()
        filtered = [
            a for a in reports if a.processed_content and query_lower in a.processed_content.lower()
        ][:limit]

        return Result.ok(filtered)

    # ========================================================================
    # STATISTICS (Generalized)
    # ========================================================================

    @with_error_handling("get_report_statistics")
    async def get_report_statistics(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        report_type: ReportType | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Calculate report statistics for date range.

        Statistics include:
        - Total reports submitted
        - Total words written
        - Average words per report
        - Longest streak (consecutive days)
        - Current streak
        - Most productive day of week
        - Category distribution
        - Type distribution (if not filtered)

        Args:
            user_uid: User identifier
            start_date: Start date for analysis
            end_date: End date for analysis
            report_type: Optional type filter (JOURNAL, ESSAY, etc.)

        Returns:
            Result containing statistics dictionary
        """
        # Get all reports in date range
        reports_result = await self.list_reports_by_date_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            report_type=report_type,
            limit=QueryLimit.COMPREHENSIVE,  # Large enough for most use cases
        )

        if reports_result.is_error:
            return Result.fail(reports_result.expect_error())

        reports = reports_result.value

        # Calculate statistics
        total_reports = len(reports)
        if total_reports == 0:
            return Result.ok(
                {
                    "total_reports": 0,
                    "total_words": 0,
                    "average_words": 0,
                    "longest_streak": 0,
                    "current_streak": 0,
                    "reports_by_day_of_week": {},
                    "reports_by_category": {},
                    "reports_by_type": {},
                }
            )

        # Total words
        total_words = sum(
            len(a.processed_content.split()) if a.processed_content else 0 for a in reports
        )
        average_words = total_words / total_reports if total_reports > 0 else 0

        # Streak calculation
        report_dates = sorted([a.created_at.date() for a in reports])
        longest_streak = self._calculate_longest_streak(report_dates)
        current_streak = self._calculate_current_streak(report_dates)

        # Day of week distribution
        day_of_week_counts = {}
        for a in reports:
            day_name = a.created_at.strftime("%A")
            day_of_week_counts[day_name] = day_of_week_counts.get(day_name, 0) + 1

        # Category distribution
        category_counts = {}
        for a in reports:
            if a.metadata and "category" in a.metadata:
                category = a.metadata["category"]
                category_counts[category] = category_counts.get(category, 0) + 1

        # Type distribution (only if not filtered by type)
        type_counts = {}
        if not report_type:
            for a in reports:
                type_name = a.report_type.value
                type_counts[type_name] = type_counts.get(type_name, 0) + 1

        return Result.ok(
            {
                "total_reports": total_reports,
                "total_words": total_words,
                "average_words": round(average_words, 1),
                "longest_streak": longest_streak,
                "current_streak": current_streak,
                "reports_by_day_of_week": day_of_week_counts,
                "reports_by_category": category_counts,
                "reports_by_type": type_counts,
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

        # Check if last report was today or yesterday
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
    # RECENT REPORTS
    # ========================================================================

    @with_error_handling("get_recent_reports")
    async def get_recent_reports(
        self,
        user_uid: str,
        report_type: ReportType | None = None,
        limit: int = 10,
    ) -> Result[list[Report]]:
        """
        Get most recent reports.

        Args:
            user_uid: User identifier
            report_type: Optional type filter (JOURNAL, ESSAY, etc.)
            limit: Max results (default 10)

        Returns:
            Result containing list of recent reports
        """
        # Build query filters
        filters = {
            "user_uid": user_uid,
            "limit": limit,
            "sort_by": "created_at",
            "sort_order": "desc",
        }
        if report_type:
            filters["report_type"] = report_type.value

        return await self.backend.find_by(**filters)

    # ========================================================================
    # CROSS-DOMAIN QUERIES
    # ========================================================================

    @with_error_handling("get_journal_for_report")
    async def get_journal_for_report(
        self,
        report_uid: str,
        user_uid: str,
    ) -> Result[dict[str, Any] | None]:
        """
        Get the Journal created from processing this report.

        Journals store source report UID in metadata.source_report_uid.
        This is a cross-domain query serving the Report use case.

        Args:
            report_uid: The report UID to find journal for
            user_uid: User UID for ownership verification

        Returns:
            Result containing journal dict {uid, content, metadata, created_at} or None
        """
        driver = self.backend.driver

        cypher = """
        MATCH (j:Journal {user_uid: $user_uid})
        WHERE j.metadata IS NOT NULL
          AND j.metadata CONTAINS $report_uid
        RETURN j.uid as uid, j.content as content,
               j.metadata as metadata, j.created_at as created_at
        ORDER BY j.created_at DESC
        LIMIT 1
        """

        async with driver.session() as session:
            result = await session.run(cypher, user_uid=user_uid, report_uid=report_uid)
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
