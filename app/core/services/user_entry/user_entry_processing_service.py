"""
UserEntryProcessingService — ADR-054 Step 5
============================================

Pipeline dispatcher for ``UserEntry``. Reads ``entry.pipeline`` and routes
to the matching processor:

    Pipeline.NONE                     → no-op (already complete)
    Pipeline.TRANSCRIBE               → Deepgram transcription (Step 11+)
    Pipeline.TRANSCRIBE_AND_STRUCTURE → transcribe + LLM structuring (Step 11+)
    Pipeline.LLM_SUMMARY              → LLM summarization (Step 11+)
    Pipeline.TEACHER_REVIEW           → no-op (waits on teacher queue)

Step 5 scope
------------
The additive through-Step-13 discipline keeps the legacy
``SubmissionsProcessingService`` and ``JournalOutputService`` in place.
This dispatcher is a real entry point for ``NONE`` and ``TEACHER_REVIEW``
(which are legitimately no-ops), and returns a clear
``not-yet-implemented`` error for the Deepgram / LLM pipelines. Those
get wired in a later step when the legacy handlers are retired.

See: /home/mike/.claude/plans/woolly-weaving-hejlsberg.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.user_entry.user_entry_service import UserEntryService


class UserEntryProcessingService:
    """Pipeline dispatcher for ``UserEntry``.

    Composed with ``UserEntryService`` so NONE / TEACHER_REVIEW paths can
    return the freshly-fetched entry without re-reading. The deepgram /
    LLM pipelines will be wired in Step 11 once the legacy processing
    services are retired.
    """

    def __init__(self, entry_service: UserEntryService) -> None:
        self.entry_service = entry_service
        self.logger = get_logger("skuel.services.user_entry.processing")  # type: ignore[assignment]

    async def process(
        self,
        entry: UserEntry,
        instructions: str | None = None,
    ) -> Result[UserEntry]:
        """Run ``entry.pipeline`` on ``entry``.

        Args:
            entry: The UserEntry to process.
            instructions: Per-run override for pipeline instructions
                (e.g., custom LLM prompt). Falls back to ``entry.instructions``.

        Returns:
            Result[UserEntry] — the (possibly updated) entry.
        """
        pipeline = entry.pipeline

        if pipeline == Pipeline.NONE:
            return Result.ok(entry)

        if pipeline == Pipeline.TEACHER_REVIEW:
            # No machine processing — entry stays in 'submitted' waiting
            # on the teacher review queue.
            return Result.ok(entry)

        if pipeline in (
            Pipeline.TRANSCRIBE,
            Pipeline.TRANSCRIBE_AND_STRUCTURE,
            Pipeline.LLM_SUMMARY,
        ):
            # Wired in a later migration step; legacy
            # JournalOutputService + SubmissionsProcessingService still
            # handle these code paths for the legacy entity types.
            return Result.fail(
                Errors.business(
                    rule="user_entry_pipeline_not_yet_wired",
                    message=(
                        f"Pipeline {pipeline.value} is not yet handled by "
                        "UserEntryProcessingService. See ADR-054 Step 11."
                    ),
                )
            )

        return Result.fail(
            Errors.validation(
                f"Unknown pipeline: {pipeline}",
                field="pipeline",
            )
        )
