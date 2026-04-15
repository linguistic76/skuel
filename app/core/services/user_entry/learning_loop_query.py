"""
UserEntry Learning Loop Query Service — ADR-054 Commit 6a
==========================================================

Read-only queries that traverse the five-phase learning loop graph:

    PathStep → Exercise → UserEntry → Interaction → Report → RevisedExercise

Ported from ``LearningLoopQueryService`` unchanged — the backing Cypher is
label-agnostic and works against ``:Entity`` regardless of subtype. Only
the ``submission_type`` filter is updated to include USER_ENTRY alongside
EXERCISE_SUBMISSION for the additive-through-6a window.
"""

from core.constants import QueryLimit
from core.models.enums.entity_enums import EntityType
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry import UserEntry
from core.ports import BackendOperations
from core.ports.query_types import PathStepSubmissionRow
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.user_entry.learning_loop_query")


class LearningLoopQueryService:
    """Read-side queries for the five-phase learning loop."""

    def __init__(
        self,
        user_entry_backend: BackendOperations[UserEntry],
    ) -> None:
        self.backend = user_entry_backend
        self.logger = logger

    @with_error_handling("get_submissions_for_path_step")
    async def get_submissions_for_path_step(
        self,
        user_uid: UserUID,
        ps_uid: str,
        limit: int = QueryLimit.COMPREHENSIVE,
    ) -> Result[list[PathStepSubmissionRow]]:
        """Get a user's entries that occurred during a specific PathStep."""
        result = await self.backend.get_submissions_for_path_step(  # type: ignore[attr-defined]
            user_uid=user_uid,
            ps_uid=ps_uid,
            submission_type=EntityType.EXERCISE_SUBMISSION.value,
            limit=limit,
        )
        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            [
                PathStepSubmissionRow(
                    uid=record["uid"],
                    title=record.get("title"),
                    status=record.get("status"),
                    created_at=record.get("created_at"),
                    exercise_uid=record.get("exercise_uid"),
                    exercise_title=record.get("exercise_title"),
                    report_uid=record.get("report_uid"),
                    report_outcome=record.get("report_outcome"),
                )
                for record in result.value or []
            ]
        )
