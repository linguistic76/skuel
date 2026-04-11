"""
Submissions Search Service
============================

Service for querying submissions across all types.

Core Capabilities:
- Query submissions by date, date range, recency
- Full-text search across submission content (case-insensitive)
- Calculate statistics (streaks, word count, etc.)
- Enrich submissions with teacher-feedback counts for review UI

Filtering is pushed into Cypher via either `find_by(**operators)` or raw
parameterized queries — never by fetching a superset and post-filtering in
Python. The backend label is `:Entity`, so every query must carry an explicit
`entity_type = $submission_type` predicate or it will scan all user-owned
entities.

Timestamp invariant
-------------------
`Entity.created_at` defaults to `datetime.now()` (naive local) and is
serialized via `.isoformat()` with no tz suffix. This service builds its
date-boundary bounds the same way so ISO-string comparisons stay consistent.
If the storage invariant ever changes to tz-aware, every `datetime.combine(...)
.isoformat()` call here must be updated in lockstep — string comparison across
a tz-aware and a naive value is silently broken at day boundaries.

Methods like `get_reports_by_mood`/`get_reports_by_category` that used to live
here were removed when the journal domain was extracted — `metadata.mood` and
`metadata.category` belong to JeInput/JeOutput now, not ExerciseSubmission.
"""

from datetime import date, datetime, time, timedelta
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
from core.ports.query_types import SubmissionStatistics
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.neo4j_mapper import from_neo4j_node
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.services.submissions_search")

# Hard ceiling for caller-supplied `limit` values. A misconfigured caller
# passing an unbounded limit would otherwise drag the user's entire submission
# history through the driver. QueryLimit.MAXIMUM (10_000) is the project-wide
# "admin only" bound and is well above any legitimate UI use case.
_MAX_LIMIT = QueryLimit.MAXIMUM


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

    # Entity types this service is allowed to query. FORM_SUBMISSION is a
    # distinct domain (FormSubmissionService) and must not be reachable via
    # an `entity_type=` override — a silent cross-domain bleed would return
    # foreign rows typed as `SubmissionEntity` to the caller.
    _ALLOWED_SUBMISSION_TYPES: ClassVar[frozenset[EntityType]] = frozenset(
        {EntityType.EXERCISE_SUBMISSION}
    )

    def _resolve_submission_type(self, entity_type: EntityType | None) -> str:
        """Return the Cypher-facing entity_type string.

        Defaults to EXERCISE_SUBMISSION (the only concrete leaf in today's
        SubmissionEntity union). Never inline entity-type literals into queries
        — SKUEL014 — keep the enum as the single source of truth.

        Raises:
            ValueError: if the caller passes an EntityType that is not a
                submission type (e.g. TASK, GOAL, FORM_SUBMISSION). Caught by
                ``@with_error_handling`` and returned as a validation Result.
        """
        resolved = entity_type or EntityType.EXERCISE_SUBMISSION
        if resolved not in self._ALLOWED_SUBMISSION_TYPES:
            raise ValueError(
                f"entity_type={resolved.value!r} is not a submission type. "
                f"Allowed: {sorted(t.value for t in self._ALLOWED_SUBMISSION_TYPES)}"
            )
        return resolved.value

    @with_error_handling("get_report_for_date")
    async def get_report_for_date(
        self,
        user_uid: UserUID,
        target_date: date,
        entity_type: EntityType | None = None,
    ) -> Result[Entity | None]:
        """Get the most recent submission whose created_at falls on ``target_date``.

        Filters at the database level — previous implementations fetched the
        single newest row and then silently returned ``None`` whenever its date
        didn't match. This version only returns ``None`` when there genuinely
        is no submission on that day.

        Args:
            user_uid: Owner of the submissions.
            target_date: Calendar day to match.
            entity_type: Optional type override; defaults to EXERCISE_SUBMISSION.

        Returns:
            Result containing the newest matching submission or ``None``.
        """
        start_iso = datetime.combine(target_date, time.min).isoformat()
        end_iso = datetime.combine(target_date + timedelta(days=1), time.min).isoformat()

        result = await self.backend.find_by(
            user_uid=user_uid,
            entity_type=self._resolve_submission_type(entity_type),
            created_at__gte=start_iso,
            created_at__lt=end_iso,
            sort_by="created_at",
            sort_order="desc",
            limit=1,
        )
        if result.is_error:
            return Result.fail(result)

        submissions = result.value or []
        return Result.ok(submissions[0] if submissions else None)

    @with_error_handling("list_reports_by_date_range")
    async def list_reports_by_date_range(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        entity_type: EntityType | None = None,
        limit: int = QueryLimit.COMPREHENSIVE,
    ) -> Result[list[Entity]]:
        """List submissions within an inclusive date range.

        Both ``start_date`` and ``end_date`` are inclusive (the range ``[start,
        end]``). Filtering happens at the database — the previous implementation
        fetched a superset and post-filtered in Python.

        Args:
            user_uid: Owner of the submissions.
            start_date: Earliest day to include (inclusive).
            end_date: Latest day to include (inclusive).
            entity_type: Optional type override; defaults to EXERCISE_SUBMISSION.
            limit: Max rows to return (default ``QueryLimit.COMPREHENSIVE``).

        Returns:
            Result containing submissions newest-first.
        """
        if start_date > end_date:
            return Result.fail(
                Errors.validation(
                    message=f"start_date ({start_date}) must be <= end_date ({end_date})",
                    field="start_date",
                    value=start_date.isoformat(),
                )
            )

        limit = max(1, min(limit, _MAX_LIMIT))

        start_iso = datetime.combine(start_date, time.min).isoformat()
        end_iso = datetime.combine(end_date + timedelta(days=1), time.min).isoformat()

        result = await self.backend.find_by(
            user_uid=user_uid,
            entity_type=self._resolve_submission_type(entity_type),
            created_at__gte=start_iso,
            created_at__lt=end_iso,
            sort_by="created_at",
            sort_order="desc",
            limit=limit,
        )
        if result.is_error:
            return Result.fail(result)

        return Result.ok(result.value or [])

    @with_error_handling("search_submissions")
    async def search_submissions(
        self,
        user_uid: UserUID,
        query: str,
        entity_type: EntityType | None = None,
        limit: int = 50,
    ) -> Result[list[Entity]]:
        """Case-insensitive substring search across ``processed_content``.

        Filtering happens inside Cypher via
        ``toLower(s.processed_content) CONTAINS toLower($query)`` — no more
        over-fetching a ``limit * 3`` superset and filtering in Python.

        Args:
            user_uid: Owner of the submissions.
            query: Substring to match (case-insensitive).
            entity_type: Optional type override; defaults to EXERCISE_SUBMISSION.
            limit: Max rows to return.

        Returns:
            Result containing matching submissions newest-first.
        """
        # Reject empty, whitespace-only, and single-char queries. A bare
        # `if not query:` would let `"   "` through and trigger a full
        # CONTAINS scan across every submission.
        query = (query or "").strip()
        if len(query) < 2:
            return Result.ok([])

        limit = max(1, min(limit, _MAX_LIMIT))

        result = await self.backend.search_submission_content(  # type: ignore[attr-defined]
            user_uid=user_uid,
            submission_type=self._resolve_submission_type(entity_type),
            query_text=query,
            limit=limit,
        )
        if result.is_error:
            return Result.fail(result)

        entities = [from_neo4j_node(record, Entity) for record in result.value or []]
        return Result.ok(entities)

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
        result = await self.backend.get_submissions_with_feedback_count(  # type: ignore[attr-defined]
            user_uid=user_uid,
            submission_type=EntityType.EXERCISE_SUBMISSION.value,
            report_type=EntityType.EXERCISE_REPORT.value,
            limit=limit,
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
    ) -> Result[SubmissionStatistics]:
        """Calculate submission statistics for a date range.

        Delegates to :meth:`list_reports_by_date_range` for the database read,
        then derives word counts, streaks, and distributions in memory. Return
        shape conforms to the ``SubmissionStatistics`` TypedDict — key names
        use the ``submissions_by_*`` prefix, not the stale ``kus_by_*`` prefix
        left over from the "everything is a Ku" era.

        Args:
            user_uid: Owner of the submissions.
            start_date: Earliest day to include (inclusive).
            end_date: Latest day to include (inclusive).
            entity_type: Optional type override; defaults to EXERCISE_SUBMISSION.

        Returns:
            Result containing submission statistics.
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

        reports = reports_result.value or []

        total_reports = len(reports)
        if total_reports == 0:
            empty: SubmissionStatistics = {
                "total": 0,
                "total_words": 0,
                "average_words": 0.0,
                "longest_streak": 0,
                "current_streak": 0,
                "submissions_by_day_of_week": {},
                "submissions_by_type": {},
                "by_type": {},
                "by_status": {},
            }
            return Result.ok(empty)

        def _word_count(k: Entity) -> int:
            pc = getattr(k, "processed_content", None)
            return len(pc.split()) if pc else 0

        total_words = sum(_word_count(k) for k in reports)
        average_words = round(total_words / total_reports, 1)

        # Defensive: driver quirks / migration artifacts can leave `created_at`
        # as a string. Skip (and log) rather than 500 the whole stats call.
        dated_reports: list[tuple[datetime, Entity]] = []
        for k in reports:
            ts = k.created_at
            if not isinstance(ts, datetime):
                self.logger.warning(
                    "submissions_search.stats_skip_non_datetime",
                    uid=getattr(k, "uid", None),
                    created_at_type=type(ts).__name__,
                )
                continue
            dated_reports.append((ts, k))

        report_dates = sorted(ts.date() for ts, _ in dated_reports)
        longest_streak = self._calculate_longest_streak(report_dates)
        current_streak = self._calculate_current_streak(report_dates)

        day_of_week_counts: dict[str, int] = {}
        for ts, _ in dated_reports:
            day_name = ts.strftime("%A")
            day_of_week_counts[day_name] = day_of_week_counts.get(day_name, 0) + 1

        type_counts: dict[str, int] = {}
        for k in reports:
            type_name = k.entity_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

        status_counts: dict[str, int] = {}
        for k in reports:
            status_name = k.status.value if k.status else "unknown"
            status_counts[status_name] = status_counts.get(status_name, 0) + 1

        stats: SubmissionStatistics = {
            "total": total_reports,
            "total_words": total_words,
            "average_words": average_words,
            "longest_streak": longest_streak,
            "current_streak": current_streak,
            "submissions_by_day_of_week": day_of_week_counts,
            "submissions_by_type": type_counts,
            "by_type": type_counts,
            "by_status": status_counts,
        }
        return Result.ok(stats)

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

    def _calculate_current_streak(self, dates: list[date], today: date | None = None) -> int:
        """Calculate current consecutive day streak ending today.

        Args:
            dates: Sorted list of submission dates.
            today: Reference "today" date. Defaults to ``date.today()`` (local
                tz). Injectable for tests and for callers in non-local tz.
        """
        if not dates:
            return 0

        today = today or date.today()
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
        """Get the user's most recent submissions.

        The ``entity_type`` filter is applied unconditionally — even when the
        caller passes ``None``, the query scopes to
        ``EntityType.EXERCISE_SUBMISSION`` so it can't bleed into Tasks, Goals,
        or any other user-owned entity sharing the ``:Entity`` label.

        Args:
            user_uid: Owner of the submissions.
            entity_type: Optional type override; defaults to EXERCISE_SUBMISSION.
            limit: Max rows to return (default 10).

        Returns:
            Result containing submissions newest-first.
        """
        limit = max(1, min(limit, _MAX_LIMIT))

        result = await self.backend.find_by(
            user_uid=user_uid,
            entity_type=self._resolve_submission_type(entity_type),
            sort_by="created_at",
            sort_order="desc",
            limit=limit,
        )
        if result.is_error:
            return Result.fail(result)

        return Result.ok(result.value or [])
