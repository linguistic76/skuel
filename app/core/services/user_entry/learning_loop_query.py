"""
UserEntry Learning Loop Query Service — ADR-054
===============================================

Read-only queries that traverse the four-phase learning loop graph:

    Exercise → UserEntry → EntryReport → RevisedExercise

PathStep is the curriculum anchor, linked via ``(PathStep)-[:HAS_EXERCISE]->(Exercise)``
(denormalized as ``Exercise.path_step_uid`` for PERSONAL scope). Interaction
nodes provide situated context for each UserEntry.

The backing Cypher (in ``UserEntryBackend``) is label-agnostic and works
against ``:Entity`` regardless of subtype; post-ADR-054 the matched rows are
``:UserEntry`` nodes.
"""

from core.constants import QueryLimit
from core.models.type_hints import UserUID
from core.ports.query_types import PathStepSubmissionRow
from core.ports.user_entry_protocols import UserEntryOperations
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.user_entry.learning_loop_query")


class LearningLoopQueryService:
    """Read-side queries for the four-phase learning loop."""

    def __init__(
        self,
        user_entry_backend: UserEntryOperations,
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
        result = await self.backend.get_entries_for_path_step(
            user_uid=user_uid,
            ps_uid=ps_uid,
            limit=limit,
        )
        if result.is_error:
            return Result.fail(result)

        def _opt_str(value: object) -> str | None:
            return str(value) if value is not None else None

        return Result.ok(
            [
                PathStepSubmissionRow(
                    uid=str(record["uid"]),
                    title=_opt_str(record.get("title")),
                    status=_opt_str(record.get("status")),
                    created_at=_opt_str(record.get("created_at")),
                    exercise_uid=_opt_str(record.get("exercise_uid")),
                    exercise_title=_opt_str(record.get("exercise_title")),
                    report_uid=_opt_str(record.get("report_uid")),
                    report_outcome=_opt_str(record.get("report_outcome")),
                )
                for record in result.value or []
            ]
        )
